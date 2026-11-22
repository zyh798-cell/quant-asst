import * as ProgressPrimitive from '@radix-ui/react-progress'
import { type ComponentPropsWithoutRef, forwardRef } from 'react'

import { cn } from '@/lib/utils'

const Progress = forwardRef<
  React.ElementRef<typeof ProgressPrimitive.Root>,
  ComponentPropsWithoutRef<typeof ProgressPrimitive.Root>
>(({ className, value, ...props }, ref) => (
  <ProgressPrimitive.Root
    ref={ref}
    className={cn('relative h-2 w-full overflow-hidden rounded-pill bg-ink-100', className)}
    {...props}
  >
    <ProgressPrimitive.Indicator
      className="h-full w-full flex-1 bg-accent transition-transform duration-base ease-linear"
      style={{ transform: `translateX(-${100 - (value || 0)}%)` }}
    />
  </ProgressPrimitive.Root>
))
Progress.displayName = ProgressPrimitive.Root.displayName

export { Progress }
