import { getLanguage, setLanguage, t } from '../../i18n'
import { cn } from '../../utils/cn'

/**
 * Two-state language control. Switching reloads the SPA so every module-level
 * label re-reads the dictionary; the choice is stored in localStorage.
 */
export default function LanguageSwitcher({ compact = false }: { compact?: boolean }) {
  const language = getLanguage()
  return (
    <div
      role="group"
      aria-label={t('Language')}
      className={cn('flex items-center rounded-lg border border-border p-0.5', compact && 'text-[10px]')}
    >
      {(['en', 'hi'] as const).map((code) => (
        <button
          key={code}
          type="button"
          onClick={() => code !== language && setLanguage(code)}
          aria-pressed={language === code}
          className={cn(
            'flex min-h-6 min-w-6 items-center justify-center rounded-md px-1.5 py-1 font-medium transition-colors',
            compact ? 'text-[10px]' : 'text-[11px]',
            language === code
              ? 'bg-accent text-white'
              : 'text-text-secondary hover:bg-raised hover:text-text-primary',
          )}
          lang={code === 'hi' ? 'hi' : 'en'}
        >
          {code === 'en' ? 'EN' : 'हिं'}
        </button>
      ))}
    </div>
  )
}
