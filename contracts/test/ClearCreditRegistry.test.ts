import { expect } from "chai";
import { ethers } from "hardhat";
import { loadFixture } from "@nomicfoundation/hardhat-network-helpers";
import type { Signer } from "ethers";

const RES = 8;
const THRESHOLD = 6000;
const id = (s: string) => ethers.id(s); // keccak256(utf8) — same mapping the backend uses
// Synthetic H3-shaped index: mode bit set, resolution in bits 52-55.
const cell = (i: number, res = RES) => (1n << 59n) | (BigInt(res) << 52n) | BigInt(i);
const cells = (from: number, n: number) => Array.from({ length: n }, (_, k) => cell(from + k));

async function deploy() {
  const [admin, backend, dev, dev2, outsider] = await ethers.getSigners();
  const reg = await ethers.deployContract("ClearCreditRegistry", [admin.address, RES, THRESHOLD]);
  await reg.grantRole(await reg.REGISTRAR_ROLE(), backend.address);
  await reg.grantRole(await reg.VERIFIER_ROLE(), backend.address);
  return { reg, admin, backend, dev, dev2, outsider };
}

async function sign(reg: any, signer: Signer, c: { projectId: string; claimHash: string; vintageYear: number; claimedCredits: bigint }) {
  const net = await ethers.provider.getNetwork();
  return signer.signTypedData(
    { name: "ClearCredit", version: "1", chainId: net.chainId, verifyingContract: await reg.getAddress() },
    { Claim: [
      { name: "projectId", type: "bytes32" },
      { name: "claimHash", type: "bytes32" },
      { name: "vintageYear", type: "uint16" },
      { name: "claimedCredits", type: "uint64" },
    ] },
    c,
  );
}

async function register(reg: any, backend: Signer, dev: Signer, name: string, vintage: number, cellIds: bigint[], credits = 1000n, finalize = true) {
  const c = { projectId: id(name), claimHash: id(`hash:${name}`), vintageYear: vintage, claimedCredits: credits };
  const sig = await sign(reg, dev, c);
  await reg.connect(backend).registerProject(c.projectId, c.claimHash, await dev.getAddress(), vintage, credits, cellIds, sig);
  if (finalize) await reg.connect(backend).finalizeRegistration(c.projectId);
  return c;
}

describe("ClearCreditRegistry", () => {
  describe("registration", () => {
    it("registers, emits events, and stores the claim", async () => {
      const { reg, backend, dev } = await loadFixture(deploy);
      const c = { projectId: id("P1"), claimHash: id("hash:P1"), vintageYear: 2023, claimedCredits: 1000n };
      const sig = await sign(reg, dev, c);
      await expect(reg.connect(backend).registerProject(c.projectId, c.claimHash, dev.address, 2023, 1000n, cells(0, 3), sig))
        .to.emit(reg, "ProjectRegistered").withArgs(c.projectId, dev.address, c.claimHash, 2023, 1000n)
        .and.to.emit(reg, "CellsAdded").withArgs(c.projectId, 3, 3);
      await expect(reg.connect(backend).finalizeRegistration(c.projectId)).to.emit(reg, "ProjectFinalized").withArgs(c.projectId, 3);
      const p = await reg.getProject(c.projectId);
      expect(p.developer).to.equal(dev.address);
      expect(p.status).to.equal(2n);
      expect(await reg.projectOfClaimHash(c.claimHash)).to.equal(c.projectId);
    });

    it("rejects a duplicate claimHash (replay under a new projectId)", async () => {
      const { reg, backend, dev } = await loadFixture(deploy);
      const c = await register(reg, backend, dev, "P1", 2023, cells(0, 2));
      const c2 = { ...c, projectId: id("P1-copy") };
      const sig = await sign(reg, dev, c2);
      await expect(reg.connect(backend).registerProject(c2.projectId, c.claimHash, dev.address, 2023, 1000n, cells(100, 2), sig))
        .to.be.revertedWithCustomError(reg, "ClaimHashExists").withArgs(c.claimHash, c.projectId);
    });

    it("rejects a duplicate projectId (exact retry of the same submission)", async () => {
      const { reg, backend, dev } = await loadFixture(deploy);
      const c = await register(reg, backend, dev, "P1", 2023, cells(0, 2));
      const sig = await sign(reg, dev, c);
      await expect(reg.connect(backend).registerProject(c.projectId, c.claimHash, dev.address, 2023, 1000n, cells(0, 2), sig))
        .to.be.revertedWithCustomError(reg, "ProjectExists");
    });

    it("blocks the same cell in the same vintage for a different project", async () => {
      const { reg, backend, dev, dev2 } = await loadFixture(deploy);
      const a = await register(reg, backend, dev, "A", 2023, cells(0, 5));
      const c = { projectId: id("B"), claimHash: id("hash:B"), vintageYear: 2023, claimedCredits: 500n };
      const sig = await sign(reg, dev2, c);
      await expect(reg.connect(backend).registerProject(c.projectId, c.claimHash, dev2.address, 2023, 500n, [cell(10), cell(4)], sig))
        .to.be.revertedWithCustomError(reg, "CellAlreadyClaimed").withArgs(cell(4), 2023, a.projectId);
      // whole tx reverted: B does not exist, cell 10 still free
      expect((await reg.getProject(c.projectId)).status).to.equal(0n);
      expect(await reg.cellClaim(cell(10), 2023)).to.equal(ethers.ZeroHash);
    });

    it("allows the same cell in a different vintage", async () => {
      const { reg, backend, dev, dev2 } = await loadFixture(deploy);
      await register(reg, backend, dev, "A", 2023, cells(0, 5));
      const b = await register(reg, backend, dev2, "B", 2024, cells(0, 5));
      expect(await reg.cellClaim(cell(0), 2024)).to.equal(b.projectId);
    });

    it("checkCells reports conflicting owners per cell", async () => {
      const { reg, backend, dev } = await loadFixture(deploy);
      const a = await register(reg, backend, dev, "A", 2023, cells(0, 2));
      expect(await reg.checkCells([cell(0), cell(9), cell(1)], 2023)).to.deep.equal([a.projectId, ethers.ZeroHash, a.projectId]);
      expect(await reg.checkCells([cell(0)], 2024)).to.deep.equal([ethers.ZeroHash]);
    });

    it("rejects a signature from someone other than the developer", async () => {
      const { reg, backend, dev, outsider } = await loadFixture(deploy);
      const c = { projectId: id("P"), claimHash: id("hash:P"), vintageYear: 2023, claimedCredits: 1000n };
      const sig = await sign(reg, outsider, c);
      await expect(reg.connect(backend).registerProject(c.projectId, c.claimHash, dev.address, 2023, 1000n, cells(0, 1), sig))
        .to.be.revertedWithCustomError(reg, "BadSignature").withArgs(outsider.address, dev.address);
    });

    it("rejects a signature over different claim fields (tampered credits)", async () => {
      const { reg, backend, dev } = await loadFixture(deploy);
      const c = { projectId: id("P"), claimHash: id("hash:P"), vintageYear: 2023, claimedCredits: 1000n };
      const sig = await sign(reg, dev, c);
      await expect(reg.connect(backend).registerProject(c.projectId, c.claimHash, dev.address, 2023, 9999n, cells(0, 1), sig))
        .to.be.revertedWithCustomError(reg, "BadSignature");
    });

    it("claimDigest matches the EIP-712 digest wallets sign", async () => {
      const { reg, dev } = await loadFixture(deploy);
      const c = { projectId: id("P"), claimHash: id("hash:P"), vintageYear: 2023, claimedCredits: 1000n };
      const sig = await sign(reg, dev, c);
      const digest = await reg.claimDigest(c.projectId, c.claimHash, 2023, 1000n);
      expect(ethers.recoverAddress(digest, sig)).to.equal(dev.address);
    });

    it("only the registrar can register", async () => {
      const { reg, dev } = await loadFixture(deploy);
      const c = { projectId: id("P"), claimHash: id("hash:P"), vintageYear: 2023, claimedCredits: 1000n };
      const sig = await sign(reg, dev, c);
      await expect(reg.connect(dev).registerProject(c.projectId, c.claimHash, dev.address, 2023, 1000n, cells(0, 1), sig))
        .to.be.revertedWithCustomError(reg, "AccessControlUnauthorizedAccount");
    });

    it("rejects zero credits", async () => {
      const { reg, backend, dev } = await loadFixture(deploy);
      const c = { projectId: id("P"), claimHash: id("hash:P"), vintageYear: 2023, claimedCredits: 0n };
      const sig = await sign(reg, dev, c);
      await expect(reg.connect(backend).registerProject(c.projectId, c.claimHash, dev.address, 2023, 0n, cells(0, 1), sig))
        .to.be.revertedWithCustomError(reg, "ZeroValue");
    });
  });

  describe("cell batching", () => {
    it("caps cells per transaction", async () => {
      const { reg, backend, dev } = await loadFixture(deploy);
      const max = Number(await reg.MAX_CELLS_PER_TX());
      const c = { projectId: id("Big"), claimHash: id("hash:Big"), vintageYear: 2023, claimedCredits: 1000n };
      const sig = await sign(reg, dev, c);
      await expect(reg.connect(backend).registerProject(c.projectId, c.claimHash, dev.address, 2023, 1000n, cells(0, max + 1), sig))
        .to.be.revertedWithCustomError(reg, "TooManyCells").withArgs(max + 1, max);
    });

    it("registers a large project across batches, then locks after finalize", async () => {
      const { reg, backend, dev } = await loadFixture(deploy);
      const c = await register(reg, backend, dev, "Big", 2023, cells(0, 300), 1000n, false);
      await reg.connect(backend).addCells(c.projectId, cells(300, 300));
      await expect(reg.connect(backend).addCells(c.projectId, cells(600, 50)))
        .to.emit(reg, "CellsAdded").withArgs(c.projectId, 50, 650);
      await reg.connect(backend).finalizeRegistration(c.projectId);
      expect((await reg.getProject(c.projectId)).cellCount).to.equal(650n);
      await expect(reg.connect(backend).addCells(c.projectId, cells(700, 1)))
        .to.be.revertedWithCustomError(reg, "WrongStatus");
    });

    it("a retried batch is a no-op, not a double count", async () => {
      const { reg, backend, dev } = await loadFixture(deploy);
      const c = await register(reg, backend, dev, "P", 2023, cells(0, 10), 1000n, false);
      await expect(reg.connect(backend).addCells(c.projectId, cells(0, 10)))
        .to.emit(reg, "CellsAdded").withArgs(c.projectId, 0, 10);
    });

    it("rejects cells at the wrong H3 resolution", async () => {
      const { reg, backend, dev } = await loadFixture(deploy);
      const c = { projectId: id("P"), claimHash: id("hash:P"), vintageYear: 2023, claimedCredits: 1000n };
      const sig = await sign(reg, dev, c);
      await expect(reg.connect(backend).registerProject(c.projectId, c.claimHash, dev.address, 2023, 1000n, [cell(0, 7)], sig))
        .to.be.revertedWithCustomError(reg, "WrongCellResolution");
    });

    it("cannot finalize with no cells", async () => {
      const { reg, backend, dev } = await loadFixture(deploy);
      const c = await register(reg, backend, dev, "P", 2023, [], 1000n, false);
      await expect(reg.connect(backend).finalizeRegistration(c.projectId)).to.be.revertedWithCustomError(reg, "ZeroValue");
    });
  });

  describe("attestations", () => {
    it("are append-only and versioned", async () => {
      const { reg, backend, dev } = await loadFixture(deploy);
      const c = await register(reg, backend, dev, "P", 2023, cells(0, 1));
      await expect(reg.connect(backend).postAttestation(c.projectId, 8200, id("ev1"), "rules-v1"))
        .to.emit(reg, "AttestationPosted").withArgs(c.projectId, 0, 8200, id("ev1"), "rules-v1", backend.address);
      await reg.connect(backend).postAttestation(c.projectId, 4000, id("ev2"), "rules-v2");
      const atts = await reg.getAttestations(c.projectId);
      expect(atts.map((a: any) => a.modelVersion)).to.deep.equal(["rules-v1", "rules-v2"]);
    });

    it("reject unauthorized callers", async () => {
      const { reg, backend, dev, outsider } = await loadFixture(deploy);
      const c = await register(reg, backend, dev, "P", 2023, cells(0, 1));
      await expect(reg.connect(outsider).postAttestation(c.projectId, 9000, id("ev"), "x"))
        .to.be.revertedWithCustomError(reg, "AccessControlUnauthorizedAccount");
    });

    it("stop working after the verifier role is revoked (key rotation)", async () => {
      const { reg, admin, backend, dev, outsider } = await loadFixture(deploy);
      const c = await register(reg, backend, dev, "P", 2023, cells(0, 1));
      await reg.connect(admin).revokeRole(await reg.VERIFIER_ROLE(), backend.address);
      await expect(reg.connect(backend).postAttestation(c.projectId, 9000, id("ev"), "x"))
        .to.be.revertedWithCustomError(reg, "AccessControlUnauthorizedAccount");
      await reg.connect(admin).grantRole(await reg.VERIFIER_ROLE(), outsider.address);
      await expect(reg.connect(outsider).postAttestation(c.projectId, 9000, id("ev"), "x")).to.emit(reg, "AttestationPosted");
    });

    it("reject scores above 100% and unknown projects", async () => {
      const { reg, backend, dev } = await loadFixture(deploy);
      const c = await register(reg, backend, dev, "P", 2023, cells(0, 1));
      await expect(reg.connect(backend).postAttestation(c.projectId, 10001, id("ev"), "x"))
        .to.be.revertedWithCustomError(reg, "ScoreOutOfRange");
      await expect(reg.connect(backend).postAttestation(id("nope"), 5000, id("ev"), "x"))
        .to.be.revertedWithCustomError(reg, "UnknownProject");
    });
  });

  describe("issuance", () => {
    async function registered() {
      const f = await loadFixture(deploy);
      const c = await register(f.reg, f.backend, f.dev, "P", 2023, cells(0, 1), 1000n);
      return { ...f, c };
    }

    it("requires an attestation", async () => {
      const { reg, dev, c } = await registered();
      await expect(reg.connect(dev).issueCredits(c.projectId, 1)).to.be.revertedWithCustomError(reg, "NoAttestation");
    });

    it("is gated by the latest attestation score", async () => {
      const { reg, backend, dev, c } = await registered();
      await reg.connect(backend).postAttestation(c.projectId, 9000, id("ev1"), "v1");
      await reg.connect(backend).postAttestation(c.projectId, 3000, id("ev2"), "v2");
      await expect(reg.connect(dev).issueCredits(c.projectId, 1))
        .to.be.revertedWithCustomError(reg, "ScoreBelowThreshold").withArgs(3000, THRESHOLD);
    });

    it("caps cumulative issuance at claimed credits", async () => {
      const { reg, backend, dev, c } = await registered();
      await reg.connect(backend).postAttestation(c.projectId, 9000, id("ev"), "v1");
      await expect(reg.connect(dev).issueCredits(c.projectId, 600)).to.emit(reg, "CreditsIssued").withArgs(c.projectId, 600, 600);
      await expect(reg.connect(dev).issueCredits(c.projectId, 401))
        .to.be.revertedWithCustomError(reg, "ExceedsClaimed").withArgs(1001, 1000);
      await reg.connect(dev).issueCredits(c.projectId, 400);
    });

    it("only the developer can issue", async () => {
      const { reg, backend, outsider, c } = await registered();
      await reg.connect(backend).postAttestation(c.projectId, 9000, id("ev"), "v1");
      await expect(reg.connect(outsider).issueCredits(c.projectId, 1)).to.be.revertedWithCustomError(reg, "NotDeveloper");
    });

    it("is blocked while registration is pending", async () => {
      const { reg, backend, dev } = await loadFixture(deploy);
      const c = await register(reg, backend, dev, "P", 2023, cells(0, 1), 1000n, false);
      await reg.connect(backend).postAttestation(c.projectId, 9000, id("ev"), "v1");
      await expect(reg.connect(dev).issueCredits(c.projectId, 1)).to.be.revertedWithCustomError(reg, "WrongStatus");
    });

    it("threshold is admin-only and bounded", async () => {
      const { reg, admin, outsider } = await loadFixture(deploy);
      await expect(reg.connect(outsider).setIssueThreshold(1)).to.be.revertedWithCustomError(reg, "AccessControlUnauthorizedAccount");
      await expect(reg.connect(admin).setIssueThreshold(10001)).to.be.revertedWithCustomError(reg, "ScoreOutOfRange");
      await expect(reg.connect(admin).setIssueThreshold(7000)).to.emit(reg, "IssueThresholdChanged").withArgs(THRESHOLD, 7000);
    });
  });

  describe("retirement", () => {
    async function issued(amount: bigint) {
      const f = await loadFixture(deploy);
      const c = await register(f.reg, f.backend, f.dev, "P", 2023, cells(0, 1), 1000n);
      await f.reg.connect(f.backend).postAttestation(c.projectId, 9000, id("ev"), "v1");
      await f.reg.connect(f.dev).issueCredits(c.projectId, amount);
      return { ...f, c };
    }

    it("assigns sequential, non-overlapping serial ranges", async () => {
      const { reg, dev, c } = await issued(500n);
      await expect(reg.connect(dev).retireCredits(c.projectId, 100, "Acme Corp"))
        .to.emit(reg, "Retired").withArgs(c.projectId, dev.address, 0, 100, "Acme Corp");
      await expect(reg.connect(dev).retireCredits(c.projectId, 250, "City of Ankara"))
        .to.emit(reg, "Retired").withArgs(c.projectId, dev.address, 100, 250, "City of Ankara");
      const r = await reg.getRetirements(c.projectId);
      expect(r.map((x: any) => [x.serialStart, x.amount])).to.deep.equal([[0n, 100n], [100n, 250n]]);
    });

    it("blocks over-retirement (double retirement)", async () => {
      const { reg, dev, c } = await issued(500n);
      await reg.connect(dev).retireCredits(c.projectId, 500, "Acme");
      await expect(reg.connect(dev).retireCredits(c.projectId, 1, "Acme again"))
        .to.be.revertedWithCustomError(reg, "ExceedsIssued").withArgs(501, 500);
    });

    it("only the developer can retire, and not zero", async () => {
      const { reg, dev, outsider, c } = await issued(500n);
      await expect(reg.connect(outsider).retireCredits(c.projectId, 1, "x")).to.be.revertedWithCustomError(reg, "NotDeveloper");
      await expect(reg.connect(dev).retireCredits(c.projectId, 0, "x")).to.be.revertedWithCustomError(reg, "ZeroValue");
    });
  });
});
