// Phone photos are shrunk to a JPEG before upload (C21): iPhone HEIC files and 5–20 MB camera images were rejected
// by the server (JPEG/PNG/WebP up to 8 MB) and slow on 4G. At most 1600 px on the long side is plenty for a quote.
export const MAX_SIDE = 1600

// [width, height] scaled down to fit MAX_SIDE, never up
export function fitSize(w, h, max = MAX_SIDE) {
  if (!w || !h) return [w, h]
  const k = Math.min(1, max / Math.max(w, h))
  return [Math.round(w * k), Math.round(h * k)]
}

// The photo as a JPEG Blob; the original file if the browser can't decode it (the server then says why).
export async function shrinkPhoto(file, { max = MAX_SIDE, quality = 0.82 } = {}) {
  try {
    const img = await decode(file)
    const [w, h] = fitSize(img.width, img.height, max)
    const canvas = document.createElement('canvas')
    canvas.width = w
    canvas.height = h
    canvas.getContext('2d').drawImage(img, 0, 0, w, h)
    img.close?.()
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', quality))
    return blob && blob.size ? blob : file
  } catch {
    return file
  }
}

async function decode(file) {
  if (typeof createImageBitmap === 'function') {
    try {
      return await createImageBitmap(file, { imageOrientation: 'from-image' }) // keeps the camera's rotation
    } catch { /* not decodable this way: try an <img> */ }
  }
  const url = URL.createObjectURL(file)
  try {
    const img = new Image()
    img.src = url
    await img.decode()
    return img
  } finally {
    URL.revokeObjectURL(url)
  }
}
