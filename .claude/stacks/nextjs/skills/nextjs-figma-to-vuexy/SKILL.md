---
name: nextjs-figma-to-vuexy
description: >
  Lấy design từ Figma MCP hoặc Figma Power và parse thành code chuẩn Vuexy Next.js (MUI + TypeScript).
  Tự động call get_design_context + get_screenshot, phân tích layout, rồi map sang
  Vuexy patterns: MUI components + Tailwind Logical Properties, @core, Tabler icons, App Router.
  Dùng khi nhận Figma URL từ design team và cần generate view/page component cho CMS.
tags: [frontend, nextjs, figma]
---

# Figma to Vuexy Next.js Converter

Workflow chuyển đổi Figma design sang Vuexy Next.js TypeScript code chuẩn.

## Tech Stack CMS

- Framework: Next.js 14 (App Router)
- UI Library: MUI v6 (`@mui/material`)
- Styling: Tailwind CSS Logical Properties + MUI `sx` (xem chi tiết bên dưới)
- Icons: Tabler Icons qua Iconify class — `<i className='tabler-{name}' />`
- Charts: ApexCharts qua `AppReactApexCharts` (dynamic import bắt buộc)
- Custom components: `CustomAvatar`, `OptionMenu` từ `@core/components/`
- Types: `ThemeColor`, `SystemMode` từ `@core/types`
- Vuexy source: `apps/cms/libs/vuexy-*/next-version/typescript-version/full-version/src/`


## Styling Convention: Tailwind + MUI

Vuexy dùng Tailwind CSS Logical Properties cho layout và MUI `sx` cho theming. Đây là pattern quan trọng nhất — khác với pure MUI sx.

### Tailwind className — dùng cho layout/spacing

```tsx
// Flexbox layout
className='flex items-center justify-between gap-4'
className='flex flex-col gap-6 is-full'

// Logical spacing (Vuexy convention)
// pbe-0   = padding-block-end: 0
// plb-2   = padding-block: 0.5rem
// mlb-4   = margin-block: 1rem
// mbe-2   = margin-block-end: 0.5rem
// mie-2   = margin-inline-end: 0.5rem
// is-full = inline-size: 100%
className='pbe-0 mbe-4 is-full'

// Text utilities
className='font-medium text-xl text-balance'

// Conditional classes — dùng classnames package
className={classnames('tabler-chevron-up', item.trend === 'negative' ? 'text-error' : 'text-success')}
```

### MUI sx — dùng cho theme tokens và responsive

```tsx
sx={{ color: 'text.primary' }}
sx={{ bgcolor: 'background.paper' }}
sx={{ borderColor: 'divider' }}
sx={{ px: { xs: 2, md: 8, lg: 16 } }}
sx={{ boxShadow: 'var(--mui-customShadows-sm)' }}
sx={{ borderRadius: 2 }}
```

### Anti-patterns

```tsx
// Sai — hardcode hex
sx={{ color: '#171a1f', backgroundColor: '#f3f4f6' }}
sx={{ fontFamily: 'Inter', fontSize: '14px' }}
sx={{ boxShadow: '0px 0px 2px rgba(23,26,31,0.12)' }}
sx={{ px: '128px' }}

// Sai — dùng sx cho layout thay vì Tailwind
sx={{ display: 'flex', gap: 16 }}

// Đúng
className='flex items-center gap-4'
sx={{ color: 'text.primary', bgcolor: 'background.default' }}
```


## Step 1: Extract Figma URL

Từ URL dạng `https://www.figma.com/design/:fileKey/:fileName?node-id=1-2`:
- `fileKey` = phần `:fileKey` trong URL
- `nodeId` = `1-2` (giữ nguyên dấu `-`, Figma MCP tự xử lý)

## Step 2: Call Figma MCP

Gọi theo thứ tự:

1. `get_design_context(fileKey, nodeId)` — layout, spacing, colors, typography, component hints
2. `get_screenshot(fileKey, nodeId)` — visual reference, giữ làm ground truth để validate cuối

Nếu response quá lớn: dùng `get_metadata` trước để lấy node map, rồi fetch từng child node.

Output từ Figma MCP là reference code (React + Tailwind thuần). Phải adapt sang Vuexy MUI + Tailwind Logical Properties — không copy raw.

## Step 2b: CRITICAL — Verify Nesting trước khi code

Trước khi implement, đọc screenshot và xác nhận parent-child containment:

> "Section B có nằm **bên trong** container A không?"

Dựa vào **visual bounds** trên screenshot — KHÔNG chỉ dựa vào thứ tự text của
`get_design_context` (text có thể flatten hierarchy).

### Lỗi thường gặp khi đọc Figma — cần tránh

| Tình huống | Sai | Đúng |
|-----------|-----|------|
| Component B xuất hiện ngay sau A trong text | Implement B là sibling của A | Cross-check screenshot: B có nằm trong bounds của A không? |
| Card chứa nhiều section | Đóng thẻ card trước section cuối | Tất cả section thuộc card phải nằm trong cùng wrapper |
| Widget lồng trong panel | Render widget ngoài panel | Xác nhận visual containment trước khi đóng thẻ parent |
| Màu Figma dùng hex tùy ý | Hardcode hex vào code | Map sang MUI token / Tailwind class |

## Step 2c: Download Assets

Sau khi có đủ `get_design_context` và `get_screenshot`, download assets trước khi implement:

- Figma MCP trả về localhost URL → dùng trực tiếp, không tạo placeholder
- SVG từ Figma → lưu vào thư mục assets của dự án
- KHÔNG thêm external CDN URL mới vào code
- KHÔNG install thêm icon package — dùng `tabler-*` đã có

## Step 3: Analyze and Map Components

### Component Mapping

| Figma Element | Vuexy Component |
|---|---|
| Card / Panel | `Card` + `CardHeader` + `CardContent` |
| Grid / Row | `Grid container spacing={6}` |
| Column | `Grid item xs={12} md={6} lg={4}` |
| Avatar với icon | `CustomAvatar skin='light' variant='rounded' color={color} size={34}` |
| Icon | `i className='tabler-{name}'` |
| Badge / Chip | `Chip` từ MUI |
| Progress bar | `LinearProgress` |
| Table | `Table` từ MUI |
| Chart | `AppReactApexCharts` (dynamic import) |
| Button primary | `Button variant='contained' color='primary'` |
| Button cancel | `Button variant='outlined' color='secondary'` |
| Dropdown menu | `OptionMenu` từ `@core/components/option-menu` |
| Text | `Typography variant='h5/body1/body2/caption'` |

### Color Mapping

| Figma Color | MUI |
|---|---|
| Primary blue `#00b3ff` | `color='primary'` hoặc `color: 'primary.main'` |
| Success green | `color='success'` |
| Warning orange | `color='warning'` |
| Error red | `color='error'` |
| Info | `color='info'` |
| Secondary/gray | `color='secondary'` |
| Text dark `#171a1f` | `color='text.primary'` |
| Text muted `#565e6c` | `color='text.secondary'` |
| Text disabled | `color='text.disabled'` |


## Step 4: Generate Code

### File Structure

```
apps/cms/src/
├── app/(dashboard)/
│   └── {domain}/{feature}/
│       └── page.tsx              <- Server Component, thin, chỉ compose views
└── views/{domain}/
    └── {feature}/
        └── {ComponentName}.tsx   <- View component ('use client' nếu interactive)
```

### Page Template (Server Component)

```tsx
// MUI Imports
import Grid from '@mui/material/Grid'

// Views Imports
import FeatureView from '@views/{domain}/{feature}/FeatureView'

// Server Action Imports
import { getServerMode } from '@core/utils/serverHelpers'

const FeaturePage = async () => {
  const serverMode = getServerMode()

  return (
    <Grid container spacing={6}>
      <Grid item xs={12} md={8}>
        <FeatureView serverMode={serverMode} />
      </Grid>
    </Grid>
  )
}

export default FeaturePage
```

### Static View Component (Server Component)

```tsx
// MUI Imports
import Card from '@mui/material/Card'
import CardHeader from '@mui/material/CardHeader'
import CardContent from '@mui/material/CardContent'
import Typography from '@mui/material/Typography'

// Third-party Imports
import classnames from 'classnames'

// Core Imports
import type { ThemeColor } from '@core/types'
import CustomAvatar from '@core/components/mui/Avatar'
import OptionMenu from '@core/components/option-menu'

type DataType = {
  title: string
  subtitle: string
  icon: string
  color: ThemeColor
}

const data: DataType[] = [
  { title: 'Metric A', subtitle: '1,230', icon: 'tabler-users', color: 'primary' },
  { title: 'Metric B', subtitle: '980', icon: 'tabler-trending-up', color: 'success' },
]

const StatsCard = () => {
  return (
    <Card>
      <CardHeader
        title='Tiêu đề'
        subheader='Mô tả phụ'
        action={<OptionMenu options={['Last Week', 'Last Month']} />}
      />
      <CardContent className='flex flex-col gap-4'>
        {data.map((item, index) => (
          <div key={index} className='flex items-center gap-4'>
            <CustomAvatar skin='light' variant='rounded' color={item.color} size={34}>
              <i className={classnames(item.icon, 'text-[22px]')} />
            </CustomAvatar>
            <div className='flex flex-col'>
              <Typography className='font-medium' color='text.primary'>
                {item.title}
              </Typography>
              <Typography variant='body2'>{item.subtitle}</Typography>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

export default StatsCard
```


### Interactive View with Chart ('use client')

```tsx
'use client'

// Next Imports
import dynamic from 'next/dynamic'

// MUI Imports
import Card from '@mui/material/Card'
import CardHeader from '@mui/material/CardHeader'
import CardContent from '@mui/material/CardContent'
import { useColorScheme, useTheme } from '@mui/material/styles'

// Third-party Imports
import type { ApexOptions } from 'apexcharts'

// Core Imports
import type { SystemMode } from '@core/types'
import OptionMenu from '@core/components/option-menu'
import { rgbaToHex } from '@/utils/rgbaToHex'

// Dynamic import — bắt buộc cho ApexCharts
const AppReactApexCharts = dynamic(() => import('@/libs/styles/AppReactApexCharts'))

type Props = { serverMode: SystemMode }

const SalesChart = ({ serverMode }: Props) => {
  const theme = useTheme()
  const { mode } = useColorScheme()
  const _mode = (mode === 'system' ? serverMode : mode) || serverMode

  const options: ApexOptions = {
    chart: { toolbar: { show: false } },
    colors: [theme.palette.primary.main],
    xaxis: {
      labels: {
        style: { colors: rgbaToHex(`rgb(${theme.mainColorChannels[_mode]} / 0.4)`) }
      }
    }
  }

  return (
    <Card>
      <CardHeader
        title='Sales Chart'
        action={<OptionMenu options={['Last Week', 'Last Month']} />}
        className='pbe-0'
      />
      <CardContent>
        <AppReactApexCharts
          type='bar'
          height={200}
          width='100%'
          series={[{ data: [40, 55, 35, 65] }]}
          options={options}
        />
      </CardContent>
    </Card>
  )
}

export default SalesChart
```

### Form Page ('use client')

```tsx
'use client'

// Next Imports
import { useRouter } from 'next/navigation'

// React Imports
import { useState } from 'react'

// MUI Imports
import Card from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import Grid from '@mui/material/Grid'
import Button from '@mui/material/Button'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import CircularProgress from '@mui/material/CircularProgress'
import { toast } from 'react-toastify'

const FormView = () => {
  const router = useRouter()
  const [submitting, setSubmitting] = useState(false)

  return (
    <div>
      {/* Page Header */}
      <div className='flex items-center justify-between mbe-6'>
        <Typography variant='h4' sx={{ fontFamily: 'Archivo, sans-serif', fontWeight: 700 }}>
          Tiêu đề trang
        </Typography>
        <div className='flex gap-3'>
          <Button variant='outlined' color='secondary' onClick={() => router.back()}>
            Hủy
          </Button>
          <Button
            type='submit'
            form='main-form'
            variant='contained'
            color='primary'
            disabled={submitting}
            startIcon={
              submitting
                ? <CircularProgress size={16} color='inherit' />
                : <i className='tabler-device-floppy' />
            }
          >
            Lưu
          </Button>
        </div>
      </div>

      {/* Form */}
      <Grid container spacing={6}>
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent>
              <Typography variant='h5' className='font-semibold mbe-4'>
                <i className='tabler-info-circle mie-2' />
                Thông tin cơ bản
              </Typography>
              <Grid container spacing={4}>
                <Grid item xs={6}>
                  <Typography variant='body2' component='label' className='font-medium mbe-1 block'>
                    Tên <span style={{ color: 'var(--mui-palette-error-main)' }}>*</span>
                  </Typography>
                  <TextField fullWidth size='small' />
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography variant='h5' className='font-semibold mbe-4'>
                <i className='tabler-photo mie-2' />
                Hình ảnh
              </Typography>
              {/* image upload component */}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </div>
  )
}

export default FormView
```


## Step 5: Naming Conventions

```
Page:    {FeatureName}Page         -> BrandEditPage
View:    {Domain}{FeatureName}     -> BrandStatsCard, BrandSalesChart
File:    kebab-case.tsx            -> brand-stats-card.tsx
Folder:  kebab-case/               -> brand-management/
```

## Step 6: Import Order

```tsx
'use client' // nếu cần

// Next Imports
import dynamic from 'next/dynamic'
import { useRouter } from 'next/navigation'

// React Imports
import { useState, useEffect } from 'react'

// MUI Imports
import Card from '@mui/material/Card'
import Typography from '@mui/material/Typography'
import { useTheme, useColorScheme } from '@mui/material/styles'

// Third-party Imports
import classnames from 'classnames'
import type { ApexOptions } from 'apexcharts'
import { toast } from 'react-toastify'

// Core Imports
import type { ThemeColor, SystemMode } from '@core/types'
import CustomAvatar from '@core/components/mui/Avatar'
import OptionMenu from '@core/components/option-menu'
import { rgbaToHex } from '@/utils/rgbaToHex'

// Service Imports
import { someService } from '@/services/api/some-service'
```

## Step 7: Checklist Before Output

So sánh với `get_screenshot` đã lấy ở Step 2:

- [ ] Đã gọi `get_design_context` và `get_screenshot`
- [ ] Đã verify nesting bằng visual bounds (không chỉ dựa text)
- [ ] Đã download assets trước khi implement
- [ ] Layout khớp Figma (spacing, alignment, sizing)
- [ ] Không hardcode hex, fontFamily, fontSize, shadow string
- [ ] Layout dùng Tailwind logical classes (`flex`, `gap-4`, `is-full`, `mbe-4`)
- [ ] Colors dùng MUI tokens (`color='primary'`, `color: 'text.primary'`)
- [ ] Không hardcode spacing — dùng Tailwind/MUI scale
- [ ] Không dùng inline style không cần thiết
- [ ] Reuse component đã có trong dự án nếu phù hợp
- [ ] `'use client'` chỉ khi có hooks, event handlers, hoặc charts
- [ ] ApexCharts luôn dùng `dynamic()` import
- [ ] Icons dùng `tabler-*` class, không import SVG, không install package mới
- [ ] Server Component nhận `serverMode: SystemMode` nếu có chart
- [ ] Tên component trùng với tên file (PascalCase)
- [ ] Visual output match Figma screenshot 1:1

## Common Mistakes

| Wrong | Correct |
|---|---|
| `sx={{ display: 'flex', gap: 16 }}` | `className='flex gap-4'` |
| `sx={{ color: '#171a1f' }}` | `color='text.primary'` |
| `sx={{ fontFamily: 'Inter' }}` | Không cần — MUI theme tự handle |
| `import ApexCharts from 'apexcharts'` | `const AppReactApexCharts = dynamic(...)` |
| `className='bg-blue-500'` | `sx={{ bgcolor: 'primary.main' }}` |
| Copy raw Figma output code | Adapt sang Vuexy MUI + Tailwind Logical |
| `useState` trong Server Component | Thêm `'use client'` hoặc tách component |

## Reference Files trong Vuexy Source

```
apps/cms/libs/vuexy-*/next-version/typescript-version/full-version/src/
├── views/dashboards/analytics/
│   ├── SalesByCountries.tsx    <- Static card + Tailwind layout pattern
│   ├── SupportTracker.tsx      <- Interactive chart + CustomAvatar pattern
│   └── EarningReports.tsx      <- Chart + LinearProgress + Chip pattern
├── app/[lang]/(dashboard)/dashboards/analytics/page.tsx  <- Page pattern
└── @core/components/
    ├── mui/Avatar.tsx           <- CustomAvatar
    └── option-menu/index.tsx    <- OptionMenu
```
