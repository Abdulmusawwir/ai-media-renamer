import {
  cloneElement,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactElement,
} from "react";

interface TooltipProps {
  label: string;
  children: ReactElement;
  side?: "top" | "bottom";
  delay?: number;
}

/** Accessible tooltip for icon-only and otherwise unexplained controls. */
export function Tooltip({ label, children, side = "top", delay = 120 }: TooltipProps) {
  const id = useId();
  const [visible, setVisible] = useState(false);
  const timer = useRef<number | null>(null);

  const clearTimer = useCallback(() => {
    if (timer.current !== null) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);

  useEffect(() => clearTimer, [clearTimer]);

  const show = () => {
    clearTimer();
    timer.current = window.setTimeout(() => setVisible(true), delay);
  };
  const hide = () => {
    clearTimer();
    setVisible(false);
  };

  const original = children.props as Record<string, unknown>;
  const callOriginal = (key: string, event: unknown) => {
    const handler = original[key];
    if (typeof handler === "function") {
      (handler as (value: unknown) => void)(event);
    }
  };

  const child = cloneElement(children, {
    "aria-describedby": visible ? id : undefined,
    onMouseEnter: (event: unknown) => {
      show();
      callOriginal("onMouseEnter", event);
    },
    onMouseLeave: (event: unknown) => {
      hide();
      callOriginal("onMouseLeave", event);
    },
    onFocus: (event: unknown) => {
      show();
      callOriginal("onFocus", event);
    },
    onBlur: (event: unknown) => {
      hide();
      callOriginal("onBlur", event);
    },
  });

  return (
    <span className="ui-tooltip-wrap">
      {child}
      {visible && (
        <span role="tooltip" id={id} className={`ui-tooltip ui-tooltip-${side}`}>
          {label}
        </span>
      )}
    </span>
  );
}
