import { afterEach, describe, expect, it } from 'vitest'
import { fitSize, shrinkPhoto } from './photo.js'

describe('fitSize', () => {
  it('scales the long side down to 1600 and keeps the shape', () => {
    expect(fitSize(4000, 3000)).toEqual([1600, 1200])
    expect(fitSize(3000, 4000)).toEqual([1200, 1600])
  })
  it('never scales up', () => {
    expect(fitSize(800, 600)).toEqual([800, 600])
  })
})

describe('shrinkPhoto', () => {
  const saved = { createImageBitmap: globalThis.createImageBitmap, document: globalThis.document }
  afterEach(() => { globalThis.createImageBitmap = saved.createImageBitmap; globalThis.document = saved.document })

  it('turns a big photo into a JPEG at most 1600 px', async () => {
    let canvas
    globalThis.createImageBitmap = async () => ({ width: 4032, height: 3024, close() {} })
    globalThis.document = {
      createElement: () => (canvas = { getContext: () => ({ drawImage() {} }), toBlob: (cb, type) => cb(new Blob(['jpeg'], { type })) }),
    }
    const out = await shrinkPhoto(new Blob(['heic'], { type: 'image/heic' }))
    expect(out.type).toBe('image/jpeg')
    expect([canvas.width, canvas.height]).toEqual([1600, 1200])
  })

  it('returns the original when the browser cannot decode it', async () => {
    globalThis.createImageBitmap = async () => { throw new Error('no') }
    globalThis.document = undefined
    const file = new Blob(['raw'], { type: 'image/heic' })
    expect(await shrinkPhoto(file)).toBe(file)
  })
})
