/**
 * Coordinate conversion between documents and the screen.
 *
 * Rectangles are always stored in document coordinates. Conversion happens
 * only here so zoom, scaling and dense displays cannot move a saved mark. The
 * Python PDF parser is checked against the same coordinate fixture.
 */

export type Rotation = 0 | 90 | 180 | 270

export interface PdfRect {
  kind: 'pdf_rect'
  page: number
  x0: number
  y0: number
  x1: number
  y1: number
}

export interface ImageRect {
  kind: 'image_rect'
  page: number
  x0: number
  y0: number
  x1: number
  y1: number
}

export interface SheetRange {
  kind: 'sheet_range'
  sheet: string
  a1: string
}

export type Locator = PdfRect | ImageRect | SheetRange

/** Rectangle in screen pixels, with the origin at the top left. */
export interface ScreenRect {
  x: number
  y: number
  b: number
  h: number
}

/** Unrotated page dimensions in document coordinates. */
export interface PageSize {
  width: number
  height: number
  rotation: Rotation
}

/** Viewer scale state. */
export interface View {
  /** Zoom factor, where 1 is the original size. */
  scale: number
  /** Device pixel ratio, often 2 or more on dense displays. */
  dpr: number
}

/** Returns the visible page size in screen pixels after rotation. */
export function pageSizeOnScreen(
  page: PageSize,
  view: View,
): { width: number; height: number } {
  const f = view.scale * view.dpr
  const landscape = page.rotation === 90 || page.rotation === 270
  return {
    width: (landscape ? page.height : page.width) * f,
    height: (landscape ? page.width : page.height) * f,
  }
}

/** Converts document coordinates to screen pixels. */
export function docToScreen(
  rect: PdfRect | ImageRect,
  page: PageSize,
  view: View,
): ScreenRect {
  const { width: sb, height: sh } = page
  const width = Math.abs(rect.x1 - rect.x0)
  const height = Math.abs(rect.y1 - rect.y0)

  // Image coordinates start at the top left but still need rotation.
  if (rect.kind === 'image_rect') {
    const f = view.scale * view.dpr
    let x: number
    let y: number
    let b = width
    let h = height

    switch (page.rotation) {
      case 90:
        x = sh - rect.y1
        y = rect.x0
        b = height
        h = width
        break
      case 180:
        x = sb - rect.x1
        y = sh - rect.y1
        break
      case 270:
        x = rect.y0
        y = sb - rect.x1
        b = height
        h = width
        break
      default:
        x = rect.x0
        y = rect.y0
    }

    return { x: x * f, y: y * f, b: b * f, h: h * f }
  }

  let x: number
  let y: number
  let b: number
  let h: number

  switch (page.rotation) {
    case 90:
      x = sh - rect.y1
      y = rect.x0
      b = height
      h = width
      break
    case 180:
      x = sb - rect.x1
      y = rect.y0
      b = width
      h = height
      break
    case 270:
      x = rect.y0
      y = sb - rect.x1
      b = height
      h = width
      break
    default:
      x = rect.x0
      y = sh - rect.y1
      b = width
      h = height
  }

  const f = view.scale * view.dpr
  return { x: x * f, y: y * f, b: b * f, h: h * f }
}

/** Exact inverse of `docToScreen`. */
export function screenToDoc(
  screen: ScreenRect,
  pageSize: PageSize,
  view: View,
  pageNumber: number,
  kind: 'pdf_rect' | 'image_rect' = 'pdf_rect',
): PdfRect | ImageRect {
  const f = view.scale * view.dpr
  const x = screen.x / f
  const y = screen.y / f
  const b = screen.b / f
  const h = screen.h / f

  if (kind === 'image_rect') {
    const { width: bw, height: bh } = pageSize
    let x0: number
    let y0: number
    let x1: number
    let y1: number

    switch (pageSize.rotation) {
      case 90:
        x0 = y
        x1 = y + h
        y1 = bh - x
        y0 = bh - x - b
        break
      case 180:
        x1 = bw - x
        x0 = bw - x - b
        y1 = bh - y
        y0 = bh - y - h
        break
      case 270:
        y0 = x
        y1 = x + b
        x1 = bw - y
        x0 = bw - y - h
        break
      default:
        x0 = x
        y0 = y
        x1 = x + b
        y1 = y + h
    }

    return {
      kind: 'image_rect',
      page: pageNumber,
      x0: Math.round(x0),
      y0: Math.round(y0),
      x1: Math.round(x1),
      y1: Math.round(y1),
    }
  }

  const { width: sb, height: sh } = pageSize
  let x0: number
  let y0: number
  let x1: number
  let y1: number

  switch (pageSize.rotation) {
    case 90:
      // At 90 and 270 degrees, screen height represents document width.
      x0 = y
      x1 = y + h
      y1 = sh - x
      y0 = sh - x - b
      break
    case 180:
      x0 = sb - x - b
      x1 = sb - x
      y0 = y
      y1 = y + h
      break
    case 270:
      x0 = sb - y - h
      x1 = sb - y
      y0 = x
      y1 = x + b
      break
    default:
      x0 = x
      x1 = x + b
      y1 = sh - y
      y0 = sh - y - h
  }

  return { kind: 'pdf_rect', page: pageNumber, x0, y0, x1, y1 }
}

/** Builds a normalised rectangle from two pointer positions. */
export function rectFromPoints(
  ax: number,
  ay: number,
  bx: number,
  by: number,
): ScreenRect {
  return {
    x: Math.min(ax, bx),
    y: Math.min(ay, by),
    b: Math.abs(bx - ax),
    h: Math.abs(by - ay),
  }
}

/** Clips a rectangle to the page bounds. */
export function clampToPage(
  rect: PdfRect,
  page: PageSize,
): PdfRect {
  return {
    ...rect,
    x0: Math.max(0, Math.min(rect.x0, page.width)),
    x1: Math.max(0, Math.min(rect.x1, page.width)),
    y0: Math.max(0, Math.min(rect.y0, page.height)),
    y1: Math.max(0, Math.min(rect.y1, page.height)),
  }
}

/** Returns the smallest rectangle enclosing every supplied rectangle. */
export function mergeRects(rects: PdfRect[]): PdfRect | null {
  if (rects.length === 0) return null
  const first = rects[0]!
  return rects.slice(1).reduce<PdfRect>(
    (acc, r) => ({
      ...acc,
      x0: Math.min(acc.x0, r.x0),
      y0: Math.min(acc.y0, r.y0),
      x1: Math.max(acc.x1, r.x1),
      y1: Math.max(acc.y1, r.y1),
    }),
    { ...first },
  )
}

/**
 * The text column of a frame: the frame widened to every word on its page, so that zooming to it
 * cuts no line and keeps the label beside a value. Words of other pages or kinds are ignored.
 */
export function textColumn<R extends PdfRect | ImageRect>(frame: R, words: Locator[]): R {
  return words.reduce<R>(
    (column, word) =>
      word.kind !== 'sheet_range' && word.kind === frame.kind && word.page === frame.page
        ? { ...column, x0: Math.min(column.x0, word.x0), x1: Math.max(column.x1, word.x1) }
        : column,
    { ...frame },
  )
}

/**
 * Zoom and scroll that show the text column of a frame as large as the viewer allows: the column
 * fills `room` pixels, never below the zoom that fits the page (`fit`) and never above `max`.
 * `left` and `top` are scroll offsets in CSS pixels from the page's top-left corner that put the
 * column's centre across and the frame's centre down in the middle of the viewer.
 */
export function focusOn(
  evidence: { frame: PdfRect | ImageRect; column: PdfRect | ImageRect },
  page: PageSize,
  viewer: { width: number; height: number; room: number },
  zoom: { fit: number; max: number },
): { scale: number; left: number; top: number } {
  const frame = docToScreen(evidence.frame, page, { scale: 1, dpr: 1 })
  const column = docToScreen(evidence.column, page, { scale: 1, dpr: 1 })
  const scale = Math.min(zoom.max, Math.max(zoom.fit, viewer.room / column.b))
  return {
    scale,
    left: (column.x + column.b / 2) * scale - viewer.width / 2,
    top: (frame.y + frame.h / 2) * scale - viewer.height / 2,
  }
}
