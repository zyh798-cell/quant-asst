import { type InputHTMLAttributes, forwardRef } from 'react'

import { cn } from '@/lib/utils'

const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      ref={ref}
      className={cn(
        'flex h-11 w-full rounded-sm border border-rule bg-surface px-3 text-label text-body placeholder:text-muted focus-visible:outline-2 focus-visible:outline-ink focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...props}
    />
  ),
)
Input.displayName = 'Input'

export { Input }
