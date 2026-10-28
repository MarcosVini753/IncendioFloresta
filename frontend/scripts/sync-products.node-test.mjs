import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  mkdtemp,
  mkdir,
  cp,
  writeFile,
  readFile,
  stat,
  rm,
} from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { execFileSync } from 'node:child_process'

async function fixture(t, { sectors = false } = {}) {
  const root = await mkdtemp(path.join(tmpdir(), 'risk-sync-'))
  t.after(() => rm(root, { recursive: true, force: true }))
  const script = path.join(root, 'frontend/scripts/sync-products.mjs')
  await mkdir(path.dirname(script), { recursive: true })
  await cp(new URL('./sync-products.mjs', import.meta.url), script)
  for (const year of [2025, 2026]) {
    const dir = path.join(root, `incendio/produtos/risco/v4/${year}`)
    await mkdir(dir, { recursive: true })
    await writeFile(
      path.join(dir, 'manifest.json'),
      JSON.stringify({ schema_version: '4.0', year }),
    )
    await writeFile(
      path.join(dir, 'index.json'),
      JSON.stringify({
        year,
        sectors: [
          { id: 'AC-V4-R000C000', url: 'sectors/AC-V4-R000C000.tif', bytes: 4 },
        ],
      }),
    )
    if (sectors) {
      await mkdir(path.join(dir, 'sectors'))
      await writeFile(path.join(dir, 'sectors/AC-V4-R000C000.tif'), 'COG!')
    }
  }
  await mkdir(path.join(root, 'incendio/produtos/clima/v1/2025'), {
    recursive: true,
  })
  return {
    root,
    run(env = {}) {
      const clean = { ...process.env }
      for (const key of ['RISK_RASTER_MODE', 'RISK_RASTER_BASE_URL', 'VERCEL'])
        delete clean[key]
      return execFileSync(process.execPath, [script], {
        env: { ...clean, ...env },
        encoding: 'utf8',
        stdio: 'pipe',
      })
    },
    deployment: (year) =>
      readFile(
        path.join(root, `frontend/public/data/risk/v4/${year}/deployment.json`),
        'utf8',
      ).then(JSON.parse),
    sector: (year) =>
      path.join(
        root,
        `frontend/public/data/risk/v4/${year}/sectors/AC-V4-R000C000.tif`,
      ),
  }
}

test('explicit aggregate mode does not require TIFFs on Vercel', async (t) => {
  const f = await fixture(t)
  f.run({ VERCEL: '1', RISK_RASTER_MODE: 'aggregated' })
  for (const year of [2025, 2026]) {
    assert.deepEqual(await f.deployment(year), {
      schema_version: '1.0',
      year,
      raster_mode: 'aggregated',
      raster_base_url: null,
    })
    await assert.rejects(stat(f.sector(year)), { code: 'ENOENT' })
  }
})

test('remote mode excludes even locally available sectors and preserves year paths', async (t) => {
  const f = await fixture(t, { sectors: true })
  f.run({ VERCEL: '1', RISK_RASTER_BASE_URL: 'https://assets.example/risk/v4' })
  for (const year of [2025, 2026]) {
    assert.equal(
      (await f.deployment(year)).raster_base_url,
      `https://assets.example/risk/v4/${year}/`,
    )
    assert.equal((await f.deployment(year)).raster_mode, 'remote')
    await assert.rejects(stat(f.sector(year)), { code: 'ENOENT' })
  }
})

test('local mode still requires every COG', async (t) => {
  const f = await fixture(t)
  assert.throws(() => f.run(), /Produto v4 ausente/)
})

test('local mode copies and validates sectors', async (t) => {
  const f = await fixture(t, { sectors: true })
  f.run()
  for (const year of [2025, 2026]) {
    assert.equal(await readFile(f.sector(year), 'utf8'), 'COG!')
    assert.equal((await f.deployment(year)).raster_base_url, `/data/risk/v4/${year}/`)
    assert.equal((await f.deployment(year)).raster_mode, 'local')
  }
})

test('Vercel defaults to local sectors for both years', async (t) => {
  const f = await fixture(t, { sectors: true })
  f.run({ VERCEL: '1' })
  for (const year of [2025, 2026]) {
    assert.equal((await f.deployment(year)).raster_mode, 'local')
    assert.equal(await readFile(f.sector(year), 'utf8'), 'COG!')
  }
})

test('missing 2025 sector fails before replacing generated copies', async (t) => {
  const f = await fixture(t, { sectors: true })
  f.run()
  await rm(path.join(f.root, 'incendio/produtos/risco/v4/2025/sectors'), { recursive: true })
  assert.throws(() => f.run({ VERCEL: '1' }), /Produto v4 ausente/)
  for (const year of [2025, 2026]) {
    assert.equal(await readFile(f.sector(year), 'utf8'), 'COG!')
    assert.equal((await f.deployment(year)).raster_mode, 'local')
  }
})

test('invalid mode and credentials fail before synchronizing', async (t) => {
  const f = await fixture(t)
  assert.throws(() => f.run({ RISK_RASTER_MODE: 'typo' }), /RISK_RASTER_MODE/)
  assert.throws(
    () =>
      f.run({
        RISK_RASTER_BASE_URL: 'https://secret:password@assets.example/',
      }),
    /sem credenciais/,
  )
  assert.throws(
    () => f.run({ RISK_RASTER_MODE: 'remote' }),
    /RISK_RASTER_BASE_URL/,
  )
})

test('switching from local to aggregated removes only generated raster copies', async (t) => {
  const f = await fixture(t, { sectors: true })
  f.run()
  for (const year of [2025, 2026])
    assert.equal((await stat(f.sector(year))).size, 4)
  f.run({ RISK_RASTER_MODE: 'aggregated' })
  for (const year of [2025, 2026]) {
    await assert.rejects(stat(f.sector(year)), { code: 'ENOENT' })
    assert.equal(
      (
        await stat(
          path.join(
            f.root,
            `incendio/produtos/risco/v4/${year}/sectors/AC-V4-R000C000.tif`,
          ),
        )
      ).size,
      4,
    )
  }
})
