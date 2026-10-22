import { forwardRef, InputHTMLAttributes, ReactNode, useId } from 'react'
import { cn } from '../../utils/cn'

export interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'size'> {
  label?: string
  hint?: string
  error?: string
  leadingIcon?: ReactNode
  trailingIcon?: ReactNode
  inputSize?: 'sm' | 'md'
}

const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  {
    label,
    hint,
    error,
    leadingIcon,
    trailingIcon,
    inputSize = 'md',
    className,
    id,
    required,
    ...rest
  },
  ref,
) {
  const generatedId = useId()
  const inputId = id ?? generatedId
  const describedBy = error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined

  return (
    <div className="w-full">
      {label && (
        <label htmlFor={inputId} className="mb-1.5 block text-xs font-medium text-text-secondary">
          {label}
          {required && <span className="ml-0.5 text-risk-critical">*</span>}
        </label>
      )}
      <div className="relative">
        {leadingIcon && (
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-disabled">
            {leadingIcon}
          </span>
        )}
        <input
          ref={ref}
          id={inputId}
          required={required}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={cn(
            'w-full rounded-lg border bg-canvas text-text-primary text-sm placeholder:text-text-disabled',
            'transition-shadow focus:outline-none focus:ring-2',
            inputSize === 'sm' ? 'h-8 px-2.5' : 'h-10 px-3',
            leadingIcon ? (inputSize === 'sm' ? 'pl-8' : 'pl-9') : undefined,
            trailingIcon ? (inputSize === 'sm' ? 'pr-8' : 'pr-9') : undefined,
            error
              ? 'border-risk-critical focus:border-risk-critical focus:ring-risk-critical'
              : 'border-border focus:border-accent-ring focus:ring-accent-ring',
            className,
          )}
          {...rest}
        />
        {trailingIcon && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-text-disabled">
            {trailingIcon}
          </span>
        )}
      </div>
      {error ? (
        <p id={`${inputId}-error`} className="mt-1.5 text-xs text-risk-critical">
          {error}
        </p>
      ) : hint ? (
        <p id={`${inputId}-hint`} className="mt-1.5 text-xs text-text-secondary">
          {hint}
        </p>
      ) : null}
    </div>
  )
})

export default Input
