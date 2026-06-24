---
name: nextjs-frontend-patterns
description: >
  Frontend development patterns cho CMS — React + MUI + Vuexy template.
  Component composition, state management, data fetching, forms, error handling.
  Align với Vuexy Next.js TypeScript conventions.
tags: [frontend, nextjs]
---

# Frontend Patterns — CMS

React patterns cho CMS, align với frontend conventions và project structure conventions.

> Khi implement từ Figma URL: dùng skill `figma-to-vuexy` thay skill này.

## Stack

- Next.js 14 App Router · MUI v6 · Tailwind CSS Logical Properties
- Vuexy template: `apps/cms/libs/vuexy-*/next-version/typescript-version/full-version/src/`
- Icons: `<i className='tabler-{name}' />`
- Custom: `CustomAvatar`, `OptionMenu` từ `@core/components/`

## Component Organization

```
app/(dashboard)/{domain}/{feature}/page.tsx     ← Server Component, thin
views/{domain}/{feature}/{ComponentName}.tsx    ← View logic
components/common/                              ← Shared reusable components
components/forms/                               ← Form-specific components
```

Rules:
- Pages compose views — không chứa business logic
- Reusable UI vào `components/`
- API calls qua service layer, không trực tiếp từ component
- `'use client'` chỉ khi có hooks, event handlers, hoặc charts

## Loading / Error / Empty States

Luôn handle đủ 3 states:

```tsx
{loading && (
  <Box display='flex' flexDirection='column' gap={2}>
    <Skeleton variant='rectangular' height={40} />
    <Skeleton variant='rectangular' height={40} />
  </Box>
)}
{error && (
  <Box display='flex' justifyContent='center' py={3}>
    <Typography color='error'>{error}</Typography>
  </Box>
)}
{!loading && !error && data.length === 0 && (
  <Box display='flex' justifyContent='center' py={3}>
    <Typography color='text.secondary'>Không có dữ liệu.</Typography>
  </Box>
)}
{!loading && !error && data.length > 0 && (
  <DataList data={data} />
)}
```

## Custom Hooks

### useDebounce — cho search input

```tsx
import { useState, useEffect } from 'react'

export function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])

  return debounced
}

// Usage
const debouncedSearch = useDebounce(searchInput, 300)
useEffect(() => { fetchData(debouncedSearch) }, [debouncedSearch])
```

### useToggle

```tsx
import { useState, useCallback } from 'react'

export function useToggle(initial = false): [boolean, () => void] {
  const [value, setValue] = useState(initial)
  const toggle = useCallback(() => setValue(v => !v), [])
  return [value, toggle]
}
```

## Form Pattern (Vuexy)

```tsx
'use client'

import { useState } from 'react'
import Grid from '@mui/material/Grid'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import { toast } from 'react-toastify'

interface FormState { nameVi: string; nameEn: string }
interface FormErrors { nameVi?: string; nameEn?: string }

const FormView = () => {
  const [form, setForm] = useState<FormState>({ nameVi: '', nameEn: '' })
  const [errors, setErrors] = useState<FormErrors>({})
  const [submitting, setSubmitting] = useState(false)

  function validate(): boolean {
    const e: FormErrors = {}
    if (!form.nameVi.trim()) e.nameVi = 'Tên là bắt buộc.'
    if (!form.nameEn.trim()) e.nameEn = 'Tên EN là bắt buộc.'
    setErrors(e)
    return Object.keys(e).length === 0
  }

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!validate()) return
    setSubmitting(true)
    try {
      // await someService.create(form)
      toast.success('Tạo thành công.')
    } catch {
      toast.error('Tạo thất bại, vui lòng thử lại.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Box component='form' onSubmit={handleSubmit} noValidate>
      <Grid container spacing={4}>
        <Grid item xs={6}>
          <Typography variant='body2' component='label' className='font-medium mbe-1 block'>
            Tên <span style={{ color: 'var(--mui-palette-error-main)' }}>*</span>
          </Typography>
          <TextField
            fullWidth size='small'
            value={form.nameVi}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm(p => ({ ...p, nameVi: e.target.value }))}
            error={!!errors.nameVi}
            helperText={errors.nameVi}
          />
        </Grid>
      </Grid>
      <Button
        type='submit'
        variant='contained'
        color='primary'
        disabled={submitting}
        startIcon={submitting ? <CircularProgress size={16} color='inherit' /> : <i className='tabler-device-floppy' />}
        className='mbs-4'
      >
        Lưu
      </Button>
    </Box>
  )
}
```

## Data Fetching Pattern

```tsx
'use client'

import { useState, useEffect } from 'react'
import { someService } from '@/services/api/some-service'

const ListPage = () => {
  const [data, setData] = useState<Item[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    someService.getAll()
      .then(res => setData(res.data))
      .catch(() => setError('Lỗi hệ thống, vui lòng thử lại sau.'))
      .finally(() => setLoading(false))
  }, [])

  // render states...
}
```

## Performance

```tsx
import { useMemo, useCallback, lazy, Suspense } from 'react'

// Memoize expensive computations
const sorted = useMemo(() => [...items].sort((a, b) => b.createdAt - a.createdAt), [items])

// Memoize callbacks
const handleSearch = useCallback((q: string) => setQuery(q), [])

// Lazy load heavy components (charts, modals)
const HeavyChart = lazy(() => import('./HeavyChart'))
// <Suspense fallback={<Skeleton />}><HeavyChart /></Suspense>
```

## Checklist

- [ ] Loading, empty, error states đều handled
- [ ] Không có API calls trực tiếp từ UI component — qua service layer
- [ ] `'use client'` chỉ khi thực sự cần
- [ ] State localized, không lift lên quá cao
- [ ] Form có validation + loading state + disable double-submit
- [ ] Không hardcode hex, fontFamily, fontSize — dùng MUI tokens
- [ ] Layout dùng Tailwind className, không dùng sx cho flex/gap
