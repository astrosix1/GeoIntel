import styles from './Segmented.module.css';

export interface SegmentedOption<T extends string> {
  value: T;
  label: string;
  // Shown but not selectable, with a reason on hover (for example a choice that is not ready yet).
  disabled?: boolean;
  hint?: string;
}

// A row of mutually exclusive choices (replaces the many ad-hoc toggle rows).
export default function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
  size = 'md',
  block = false,
}: {
  options: SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  label: string;
  size?: 'md' | 'sm';
  block?: boolean;
}) {
  return (
    <div className={[styles.group, size === 'sm' && styles.sm, block && styles.block].filter(Boolean).join(' ')} role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={option.value === value}
          disabled={option.disabled}
          title={option.hint}
          className={`${styles.option} ${option.value === value ? styles.active : ''}`}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
