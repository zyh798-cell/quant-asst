import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { type ButtonHTMLAttributes, forwardRef } from 'react'

import { cn } from '@/lib/utils'

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-sm font-body font-medium transition-[color,background-color,border-color,opacity] duration-fast disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-ink focus-visible:outline-offset-2 [&_svg]:size-4 [&_svg]:shrink-0',
  {
    variants: {
      variant: {
        // 用墨变体作底、白字：--color-accent 底 + 墨字对比度仅 4.45:1，不达 AA
        primary: 'bg-accent-ink text-surface shadow-sm hover:bg-accent-ink/90',
        secondary: 'border border-rule bg-surface text-body hover:bg-accent-soft',
        ghost: 'text-accent-ink hover:bg-accent-soft',
        danger: 'bg-danger text-surface hover:bg-danger/90',
      },
      size: {
        sm: 'h-9 px-3 text-label',
        md: 'h-11 px-4 text-label',
        // 用 text-base 而非 text-body：后者在本项目是颜色类，会与 primary 的 text-surface 冲突
        lg: 'h-12 px-5 text-base',
      },
    },
    defaultVariants: { variant: 'primary', size: 'md' },
  },
)

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    return (
      <Comp className={cn(buttonVariants({ variant, size }), className)} ref={ref} {...props} />
    )
  },
)
Button.displayName = 'Button'

export { Button, buttonVariants }
