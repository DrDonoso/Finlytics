import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { PLUGIN_VIEW_REGISTRY } from './investments/registry'
import { chunksFor, createPrefetcher, pageChunks } from './routePrefetch'

type Chunk = () => Promise<unknown>

/** A prefetcher whose every path resolves to one chunk that records the path. */
function recordingPrefetcher() {
  const loaded: string[] = []
  const prefetcher = createPrefetcher(path => [() => {
    loaded.push(path)
    return Promise.resolve()
  }])
  return { loaded, prefetcher }
}

describe('chunksFor', () => {
  it('maps a route to its page', () => {
    expect(chunksFor('/')).toEqual([pageChunks['/']])
    expect(chunksFor('/settings/rules')).toEqual([pageChunks['/settings/rules']])
  })

  it('adds the connector view on a connector route', () => {
    expect(chunksFor('/investments/indexa-capital')).toEqual([
      pageChunks['/investments/:pluginId'],
      PLUGIN_VIEW_REGISTRY['indexa-capital'].load,
    ])
  })

  it('loads only the wrapper for a connector with no view', () => {
    expect(chunksFor('/investments/unknown')).toEqual([pageChunks['/investments/:pluginId']])
  })

  it('knows nothing about a route that is not a page', () => {
    expect(chunksFor('/nowhere')).toEqual([])
  })
})

describe('route', () => {
  it('loads each chunk once however often it is asked', async () => {
    const chunk = vi.fn<Chunk>(() => Promise.resolve())
    const prefetcher = createPrefetcher(() => [chunk])

    await prefetcher.route('/a')
    await prefetcher.route('/a')

    expect(chunk).toHaveBeenCalledTimes(1)
  })

  it('settles when a chunk fails, and does not ask for it again', async () => {
    const stale = vi.fn<Chunk>(() => Promise.reject(new Error('chunk removed by a deploy')))
    const prefetcher = createPrefetcher(() => [stale])

    await expect(prefetcher.route('/a')).resolves.toBeUndefined()
    await prefetcher.route('/a')

    expect(stale).toHaveBeenCalledTimes(1)
  })
})

describe('target', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('prefetches the in-app link an event started inside', () => {
    document.body.innerHTML = '<a href="/mortgage?tab=schedule"><span>Mortgage</span></a>'
    const { loaded, prefetcher } = recordingPrefetcher()

    prefetcher.target(document.querySelector('span'))

    expect(loaded).toEqual(['/mortgage'])
  })

  it('ignores a link to another site', () => {
    document.body.innerHTML = '<a href="https://example.com/mortgage">Elsewhere</a>'
    const { loaded, prefetcher } = recordingPrefetcher()

    prefetcher.target(document.querySelector('a'))

    expect(loaded).toEqual([])
  })

  it('prefetches the route a button declares', () => {
    document.body.innerHTML = '<button type="button" data-prefetch="/finances"><svg></svg></button>'
    const { loaded, prefetcher } = recordingPrefetcher()

    prefetcher.target(document.querySelector('svg'))

    expect(loaded).toEqual(['/finances'])
  })

  it('ignores anything that is not a link', () => {
    document.body.innerHTML = '<p>Plain text</p>'
    const { loaded, prefetcher } = recordingPrefetcher()

    prefetcher.target(document.querySelector('p'))
    prefetcher.target(document)
    prefetcher.target(null)

    expect(loaded).toEqual([])
  })
})

describe('whenIdle', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    Reflect.deleteProperty(navigator, 'connection')
  })

  it('prefetches one path per idle period, in order', async () => {
    const { loaded, prefetcher } = recordingPrefetcher()

    prefetcher.whenIdle(['/a', '/b'])
    expect(loaded).toEqual([])

    await vi.advanceTimersByTimeAsync(1500)
    expect(loaded).toEqual(['/a'])

    await vi.advanceTimersByTimeAsync(1500)
    expect(loaded).toEqual(['/a', '/b'])
  })

  it('stops once cancelled', async () => {
    const { loaded, prefetcher } = recordingPrefetcher()

    const cancel = prefetcher.whenIdle(['/a', '/b'])
    await vi.advanceTimersByTimeAsync(1500)
    cancel()
    await vi.advanceTimersByTimeAsync(10_000)

    expect(loaded).toEqual(['/a'])
  })

  it('does nothing when the visitor asked to save data', async () => {
    Object.defineProperty(navigator, 'connection', { value: { saveData: true }, configurable: true })
    const { loaded, prefetcher } = recordingPrefetcher()

    prefetcher.whenIdle(['/a'])
    await vi.advanceTimersByTimeAsync(10_000)

    expect(loaded).toEqual([])
  })

  it('waits for requestIdleCallback where the browser has it', () => {
    const requestIdleCallback = vi.fn(() => 7)
    const cancelIdleCallback = vi.fn()
    vi.stubGlobal('requestIdleCallback', requestIdleCallback)
    vi.stubGlobal('cancelIdleCallback', cancelIdleCallback)

    const cancel = recordingPrefetcher().prefetcher.whenIdle(['/a'])
    expect(requestIdleCallback).toHaveBeenCalledWith(expect.any(Function), { timeout: 5000 })

    cancel()
    expect(cancelIdleCallback).toHaveBeenCalledWith(7)
  })
})
