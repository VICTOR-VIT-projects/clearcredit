// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";

/// @title ClearCreditRegistry
/// @notice Tamper-evident registry of carbon-credit claims. Enforces one claim per
///         (H3 cell, vintage year), append-only integrity attestations, attestation-gated
///         issuance, and non-overlapping sequential retirement serials.
/// @dev The chain proves a record was not altered and enforces uniqueness. It does NOT
///      prove physical truth. Exact geometric overlap is checked off-chain; the cell
///      cover here is a conservative backstop (see docs/THREAT_MODEL.md).
contract ClearCreditRegistry is AccessControl, EIP712 {
    bytes32 public constant VERIFIER_ROLE = keccak256("VERIFIER_ROLE");
    bytes32 public constant REGISTRAR_ROLE = keccak256("REGISTRAR_ROLE");
    bytes32 public constant CLAIM_TYPEHASH =
        keccak256("Claim(bytes32 projectId,bytes32 claimHash,uint16 vintageYear,uint64 claimedCredits,bytes32 cellsRoot)");
    uint256 public constant MAX_CELLS_PER_TX = 300;
    uint256 public constant PENDING_EXPIRY_BLOCKS = 7200;
    uint16 public constant MAX_SCORE_BPS = 10_000;

    enum Status { None, Pending, Registered, Cancelled }

    struct Project {
        address developer;
        bytes32 claimHash;
        uint16 vintageYear;
        Status status;
        uint64 claimedCredits;
        uint64 issued;
        uint64 retired;
        uint32 cellCount;
        uint64 registeredAt;
        bytes32 cellsRoot;
        bytes32 cellsHash;
        uint64 lastCell;
        uint64 registeredBlock;
    }

    struct Attestation {
        uint16 scoreBps;
        bytes32 evidenceHash;
        string modelVersion;
        address verifier;
        uint64 timestamp;
    }

    struct Retirement {
        uint64 serialStart; // inclusive; range is [serialStart, serialStart + amount)
        uint64 amount;
        address from;
        string beneficiary;
        uint64 timestamp;
    }

    /// @notice H3 resolution every cell must use; mixing resolutions would break uniqueness.
    uint8 public immutable cellResolution;
    /// @notice Minimum latest attestation score (bps) required before credits can be issued.
    uint16 public issueThresholdBps;

    mapping(bytes32 => Project) private _projects;
    mapping(bytes32 => bytes32) public projectOfClaimHash;
    mapping(uint64 => mapping(uint16 => bytes32)) public cellClaim; // cell => vintage => projectId
    mapping(bytes32 => Attestation[]) private _attestations;
    mapping(bytes32 => Retirement[]) private _retirements;

    event ProjectRegistered(bytes32 indexed projectId, address indexed developer, bytes32 claimHash, uint16 vintageYear, uint64 claimedCredits);
    event CellsAdded(bytes32 indexed projectId, uint32 added, uint32 total);
    event ProjectFinalized(bytes32 indexed projectId, uint32 cellCount);
    event CellListCommitted(bytes32 indexed projectId, bytes32 cellsRoot);
    event PendingCancelled(bytes32 indexed projectId, address indexed caller, uint32 released, uint32 remaining);
    event AttestationPosted(bytes32 indexed projectId, uint256 index, uint16 scoreBps, bytes32 evidenceHash, string modelVersion, address indexed verifier);
    event CreditsIssued(bytes32 indexed projectId, uint64 amount, uint64 totalIssued);
    event Retired(bytes32 indexed projectId, address indexed from, uint64 serialStart, uint64 amount, string beneficiary);
    event IssueThresholdChanged(uint16 oldBps, uint16 newBps);

    error ProjectExists(bytes32 projectId);
    error ClaimHashExists(bytes32 claimHash, bytes32 existingProjectId);
    error UnknownProject(bytes32 projectId);
    error WrongStatus(bytes32 projectId, Status status);
    error BadSignature(address recovered, address developer);
    error ZeroValue();
    error TooManyCells(uint256 given, uint256 max);
    error WrongCellResolution(uint64 cell, uint8 resolution);
    error CellsNotSorted(uint64 cell, uint64 previous);
    error CellCommitmentMismatch(bytes32 expected, bytes32 actual);
    error PendingNotExpired(uint256 eligibleBlock);
    error CellAlreadyClaimed(uint64 cell, uint16 vintageYear, bytes32 existingProjectId);
    error ScoreOutOfRange(uint16 scoreBps);
    error NotDeveloper(address caller);
    error NoAttestation(bytes32 projectId);
    error ScoreBelowThreshold(uint16 scoreBps, uint16 thresholdBps);
    error ExceedsClaimed(uint64 requestedTotal, uint64 claimed);
    error ExceedsIssued(uint64 requestedTotal, uint64 issued);

    constructor(address admin, uint8 cellResolution_, uint16 issueThresholdBps_) EIP712("ClearCredit", "2") {
        if (issueThresholdBps_ > MAX_SCORE_BPS) revert ScoreOutOfRange(issueThresholdBps_);
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        cellResolution = cellResolution_;
        issueThresholdBps = issueThresholdBps_;
    }

    // ---------------------------------------------------------------- registration

    /// @notice Relayed by the backend. `signature` is the developer's EIP-712 signature over
    ///         Claim(projectId, claimHash, vintageYear, claimedCredits, cellsRoot), proving consent.
    function registerProject(
        bytes32 projectId,
        bytes32 claimHash,
        address developer,
        uint16 vintageYear,
        uint64 claimedCredits,
        bytes32 cellsRoot,
        uint64[] calldata cellIds,
        bytes calldata signature
    ) external onlyRole(REGISTRAR_ROLE) {
        if (_projects[projectId].status != Status.None) revert ProjectExists(projectId);
        if (projectOfClaimHash[claimHash] != bytes32(0)) revert ClaimHashExists(claimHash, projectOfClaimHash[claimHash]);
        if (projectId == bytes32(0) || claimHash == bytes32(0) || claimedCredits == 0 || developer == address(0)) {
            revert ZeroValue();
        }

        {
            bytes32 digest = _hashTypedDataV4(
                keccak256(abi.encode(CLAIM_TYPEHASH, projectId, claimHash, vintageYear, claimedCredits, cellsRoot))
            );
            address signer = ECDSA.recover(digest, signature);
            if (signer != developer) revert BadSignature(signer, developer);
        }
        Project storage p = _projects[projectId];
        p.developer = developer;
        p.claimHash = claimHash;
        p.vintageYear = vintageYear;
        p.status = Status.Pending;
        p.claimedCredits = claimedCredits;
        p.registeredAt = uint64(block.timestamp);
        p.cellsRoot = cellsRoot;
        p.registeredBlock = uint64(block.number);
        projectOfClaimHash[claimHash] = projectId;
        emit ProjectRegistered(projectId, developer, claimHash, vintageYear, claimedCredits);
        emit CellListCommitted(projectId, cellsRoot);

        _addCells(projectId, cellIds);
    }

    /// @notice Add further cell batches while the project is Pending (large projects).
    function addCells(bytes32 projectId, uint64[] calldata cellIds) external onlyRole(REGISTRAR_ROLE) {
        _requireStatus(projectId, Status.Pending);
        _addCells(projectId, cellIds);
    }

    function finalizeRegistration(bytes32 projectId) external onlyRole(REGISTRAR_ROLE) {
        Project storage p = _requireStatus(projectId, Status.Pending);
        if (p.cellCount == 0) revert ZeroValue();
        if (p.cellsHash != p.cellsRoot) revert CellCommitmentMismatch(p.cellsRoot, p.cellsHash);
        p.status = Status.Registered;
        emit ProjectFinalized(projectId, p.cellCount);
    }

    /// @notice After the grace period, the developer or admin can cancel a Pending
    ///         project and release its cells in bounded batches. Claim identity remains
    ///         reserved for audit; Registered projects can never be cancelled here.
    function cancelPendingRegistration(bytes32 projectId, uint64[] calldata cellIds) external {
        Project storage p = _projects[projectId];
        if (p.status == Status.None) revert UnknownProject(projectId);
        if (msg.sender != p.developer) _checkRole(DEFAULT_ADMIN_ROLE);
        if (p.status != Status.Pending && p.status != Status.Cancelled) revert WrongStatus(projectId, p.status);
        uint256 eligible = uint256(p.registeredBlock) + PENDING_EXPIRY_BLOCKS;
        if (block.number < eligible) revert PendingNotExpired(eligible);
        if (cellIds.length > MAX_CELLS_PER_TX) revert TooManyCells(cellIds.length, MAX_CELLS_PER_TX);
        p.status = Status.Cancelled;
        uint32 released;
        for (uint256 i; i < cellIds.length; ++i) {
            uint64 cell = cellIds[i];
            if (cellClaim[cell][p.vintageYear] != projectId) continue;
            delete cellClaim[cell][p.vintageYear];
            ++released;
        }
        p.cellCount -= released;
        emit PendingCancelled(projectId, msg.sender, released, p.cellCount);
    }

    /// @dev Re-adding a cell the project already owns is a no-op, so a retried batch is safe.
    function _addCells(bytes32 projectId, uint64[] calldata cellIds) private {
        uint256 n = cellIds.length;
        if (n > MAX_CELLS_PER_TX) revert TooManyCells(n, MAX_CELLS_PER_TX);
        Project storage p = _projects[projectId];
        uint16 vintage = p.vintageYear;
        uint32 added;
        for (uint256 i; i < n; ++i) {
            uint64 cell = cellIds[i];
            if (uint8((cell >> 52) & 0xF) != cellResolution) revert WrongCellResolution(cell, cellResolution);
            bytes32 owner = cellClaim[cell][vintage];
            if (owner == projectId) continue;
            if (owner != bytes32(0)) revert CellAlreadyClaimed(cell, vintage, owner);
            if (cell <= p.lastCell) revert CellsNotSorted(cell, p.lastCell);
            cellClaim[cell][vintage] = projectId;
            p.cellsHash = keccak256(abi.encodePacked(p.cellsHash, cell));
            p.lastCell = cell;
            ++added;
        }
        p.cellCount += added;
        emit CellsAdded(projectId, added, p.cellCount);
    }

    // ---------------------------------------------------------------- attestations

    function postAttestation(bytes32 projectId, uint16 scoreBps, bytes32 evidenceHash, string calldata modelVersion)
        external
        onlyRole(VERIFIER_ROLE)
    {
        if (_projects[projectId].status == Status.None) revert UnknownProject(projectId);
        if (scoreBps > MAX_SCORE_BPS) revert ScoreOutOfRange(scoreBps);
        _attestations[projectId].push(
            Attestation(scoreBps, evidenceHash, modelVersion, msg.sender, uint64(block.timestamp))
        );
        emit AttestationPosted(projectId, _attestations[projectId].length - 1, scoreBps, evidenceHash, modelVersion, msg.sender);
    }

    function setIssueThreshold(uint16 newBps) external onlyRole(DEFAULT_ADMIN_ROLE) {
        if (newBps > MAX_SCORE_BPS) revert ScoreOutOfRange(newBps);
        emit IssueThresholdChanged(issueThresholdBps, newBps);
        issueThresholdBps = newBps;
    }

    // ---------------------------------------------------------------- issuance and retirement

    /// @notice Developer self-issues, gated by the latest attestation score; capped at claimed credits.
    function issueCredits(bytes32 projectId, uint64 amount) external {
        Project storage p = _requireStatus(projectId, Status.Registered);
        if (msg.sender != p.developer) revert NotDeveloper(msg.sender);
        if (amount == 0) revert ZeroValue();
        Attestation[] storage atts = _attestations[projectId];
        if (atts.length == 0) revert NoAttestation(projectId);
        uint16 score = atts[atts.length - 1].scoreBps;
        if (score < issueThresholdBps) revert ScoreBelowThreshold(score, issueThresholdBps);
        uint64 total = p.issued + amount;
        if (total > p.claimedCredits) revert ExceedsClaimed(total, p.claimedCredits);
        p.issued = total;
        emit CreditsIssued(projectId, amount, total);
    }

    /// @notice Retires credits under the next sequential serial range, so ranges never overlap.
    function retireCredits(bytes32 projectId, uint64 amount, string calldata beneficiary) external {
        Project storage p = _projects[projectId];
        if (p.status == Status.None) revert UnknownProject(projectId);
        if (msg.sender != p.developer) revert NotDeveloper(msg.sender);
        if (amount == 0) revert ZeroValue();
        uint64 start = p.retired;
        uint64 total = start + amount;
        if (total > p.issued) revert ExceedsIssued(total, p.issued);
        p.retired = total;
        _retirements[projectId].push(Retirement(start, amount, msg.sender, beneficiary, uint64(block.timestamp)));
        emit Retired(projectId, msg.sender, start, amount, beneficiary);
    }

    // ---------------------------------------------------------------- views

    function getProject(bytes32 projectId) external view returns (Project memory) {
        return _projects[projectId];
    }

    function getAttestations(bytes32 projectId) external view returns (Attestation[] memory) {
        return _attestations[projectId];
    }

    function getRetirements(bytes32 projectId) external view returns (Retirement[] memory) {
        return _retirements[projectId];
    }

    /// @notice Pre-check used by backend and UI before submitting: for each cell, the project
    ///         that already holds it for `vintageYear`, or zero if free.
    function checkCells(uint64[] calldata cellIds, uint16 vintageYear) external view returns (bytes32[] memory owners) {
        owners = new bytes32[](cellIds.length);
        for (uint256 i; i < cellIds.length; ++i) owners[i] = cellClaim[cellIds[i]][vintageYear];
    }

    /// @notice EIP-712 digest a developer signs; exposed so clients can verify what they sign.
    function claimDigest(bytes32 projectId, bytes32 claimHash, uint16 vintageYear, uint64 claimedCredits, bytes32 cellsRoot)
        external
        view
        returns (bytes32)
    {
        return _hashTypedDataV4(keccak256(abi.encode(CLAIM_TYPEHASH, projectId, claimHash, vintageYear, claimedCredits, cellsRoot)));
    }

    function _requireStatus(bytes32 projectId, Status want) private view returns (Project storage p) {
        p = _projects[projectId];
        if (p.status != want) {
            if (p.status == Status.None) revert UnknownProject(projectId);
            revert WrongStatus(projectId, p.status);
        }
    }
}
