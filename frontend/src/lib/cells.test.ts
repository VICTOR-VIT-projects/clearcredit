import { describe, expect, it } from 'vitest'
import { cellsRoot } from './cells'

describe('sorted cell-list commitment', () => {
  it('matches the frozen Solidity/Python running-hash vector', () => {
    expect(cellsRoot(['0x880000000000001', '0x880000000000002'])).toBe('0x4daef72f2d643bda46f14233a4e222750a5cd6cdb0a013da3e731f109d7c7d9d')
  })
  it('rejects duplicates, out-of-order cells and values wider than uint64', () => {
    for (const values of [['0x2', '0x1'], ['0x1', '0x1'], ['0x10000000000000000']]) {
      expect(() => cellsRoot(values)).toThrow()
    }
  })
})
