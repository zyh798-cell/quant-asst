import { cva, type VariantProps } from 'class-variance-authority'
import { type HTMLAttributes } from 'react'

import { cn } from '@/lib/utils'

/**
 * 风险等级 / 决策徽章：一律「浅底 + 墨变体文字」（TOKENS.md 1.4）。
 * low / medium / high / critical 映射 core/schemas.py 的 RISK_LEVELS 与 RISK_LABELS_ZH。
 */
const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded-pill px-2 py-0.5 text-micro font-body font-medium',
  {
    variants: {
      variant: {
        low: 'bg-success-soft text-success-ink',
        medium: 'bg-warning-soft text-warning-ink',
        high: 'bg-danger-soft text-danger-ink',
        critical: 'bg-danger-soft text-critical-ink',
        info: 'bg-info-soft text-info-ink',
        neutral: 'bg-ink-100 text-body',
        outline: 'border border-rule text-muted',
      },
    },
    defaultVariants: { variant: 'neutral' },
  },
)

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />
}

export { Badge, badgeVariants }
