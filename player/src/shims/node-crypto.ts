// Browser stand-ins for the two node:crypto calls the pptx engine makes.
// The player only reads decks, so originalHash just needs to be a stable label.
export function randomUUID(): string {
  return crypto.randomUUID()
}

export function createHash(_algo: string) {
  let h = 0x811c9dc5
  let n = 0
  return {
    update(bytes: Uint8Array) {
      // FNV-1a over a sample of the bytes: enough to tell decks apart, cheap for 200 MB files
      const step = Math.max(1, Math.floor(bytes.length / 65536))
      for (let i = 0; i < bytes.length; i += step) h = Math.imul(h ^ bytes[i]!, 0x01000193)
      n += bytes.length
      return this
    },
    digest(_enc: string) {
      return (h >>> 0).toString(16).padStart(8, '0') + n.toString(16)
    },
  }
}
