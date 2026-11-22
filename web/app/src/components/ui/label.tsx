import * as LabelPrimitive from '@radix-ui/react-label'
import { type ComponentPropsWithoutRef, forwardRef } from 'react'

import { cn } from '@/lib/utils'

const Label = forwardRef<
  React.ElementRef<typeof LabelPrimitive.Root>,
  ComponentPropsWithoutRef<typeof LabelPrimitive.Root>
>(({ className, ...props }, ref) => (
  <LabelPrimitive.Root
    ref={ref}
    className={cn('text-label font-medium text-body', className)}
    {...props}
  />
))
Label.displayName = LabelPrimitive.Root.displayName

export { Label }
