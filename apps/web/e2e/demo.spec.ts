import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'

const env = readFileSync(new URL('../../../.demo/env', import.meta.url), 'utf8')
const password = env.split('\n').find(line => line.startsWith('SUPERUSER_PASSWORD='))?.split('=')[1]

test('synthetic catalog supports login, search, collections, and navigation', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/objects')
  await expect(page).toHaveURL(/\/login$/)
  await page.getByLabel('Email', { exact: true }).fill('admin@example.com')
  await page.getByLabel('Password', { exact: true }).fill(password!)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page).toHaveURL(/\/objects$/)
  await expect(page.getByText(/report-\d+\.json/).first()).toBeVisible()
  await page.screenshot({ path: '../../docs/images/objects.png' })
  await page.goto('/collections')
  await expect(page.getByText('Reviewed demo objects', { exact: true })).toBeVisible()
  await page.goto('/buckets')
  await expect(page.getByText('Synthetic research archive', { exact: true })).toBeVisible()
  await page.screenshot({ path: '../../docs/images/buckets.png' })
  expect(errors).toEqual([])
})
