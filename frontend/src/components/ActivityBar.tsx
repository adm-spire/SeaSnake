import type { ReactNode } from 'react';
import { FilesIcon, GearIcon, PlayIcon, Spinner } from './Icons';

interface ActivityBarProps {
  running: boolean;
  onRun: () => void;
}

interface ActivityButtonProps {
  label: string;
  active?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  children: ReactNode;
}

function ActivityButton({ label, active, disabled, onClick, children }: ActivityButtonProps) {
  return (
    <button
      type="button"
      className={`activity-button ${active ? 'active' : ''} ${disabled ? 'disabled' : ''}`}
      title={label}
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}

export function ActivityBar({ running, onRun }: ActivityBarProps) {
  return (
    <nav className="activity-bar" aria-label="Activity bar">
      <div className="activity-group">
        <ActivityButton label="Explorer" active>
          <FilesIcon />
        </ActivityButton>
        <ActivityButton label="Run conversion (Ctrl/⌘ + Enter)" onClick={onRun} disabled={running}>
          {running ? <Spinner size={20} /> : <PlayIcon />}
        </ActivityButton>
      </div>
      <div className="activity-group activity-group--bottom">
        <ActivityButton label="Settings">
          <GearIcon />
        </ActivityButton>
      </div>
    </nav>
  );
}
