import { encodePacked, keccak256, type Hex } from 'viem'

export function cellsRoot(cellIds: string[]): Hex {
  let root: Hex = `0x${'00'.repeat(32)}`
  let previous = -1n
  for (const value of cellIds) {
    if (!/^0x[0-9a-fA-F]+$/.test(value)) throw new Error('Cell IDs must be hexadecimal uint64 values.')
    const cell = BigInt(value)
    if (cell <= previous || cell >= 1n << 64n) throw new Error('Cell IDs must be sorted, unique uint64 values.')
    root = keccak256(encodePacked(['bytes32', 'uint64'], [root, cell]))
    previous = cell
  }
  return root
}
