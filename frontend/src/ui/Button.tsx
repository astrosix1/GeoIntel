import type { ButtonHTMLAttributes, ReactNode, Ref } from 'react';
import Icon from './Icon';
import type { IconName } from './Icon';
import styles from './Button.module.css';

type Variant = 'default' | 'primary' | 'quiet';
type Size = 'md' | 'sm';

interface BaseProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'> {
  variant?: Variant;
  size?: Size;
  ref?: Ref<HTMLButtonElement>;
}

function classes(variant: Variant, size: Size, icon: boolean, extra?: string) {
  return [styles.button, variant !== 'default' && styles[variant], size === 'sm' && styles.sm, icon && styles.icon, extra]
    .filter(Boolean)
    .join(' ');
}

export default function Button({
  variant = 'default',
  size = 'md',
  icon,
  className,
  children,
  type = 'button',
  ref,
  ...rest
}: BaseProps & { icon?: IconName; children?: ReactNode }) {
  return (
    <button ref={ref} type={type} className={classes(variant, size, false, className)} {...rest}>
      {icon && <Icon name={icon} size={size === 'sm' ? 14 : 16} />}
      {children}
    </button>
  );
}

// A square button with only an icon; the label is required because there is no visible text.
export function IconButton({
  icon,
  label,
  variant = 'quiet',
  size = 'md',
  className,
  type = 'button',
  ...rest
}: BaseProps & { icon: IconName; label: string }) {
  return (
    <button type={type} className={classes(variant, size, true, className)} aria-label={label} title={label} {...rest}>
      <Icon name={icon} size={size === 'sm' ? 14 : 16} />
    </button>
  );
}
