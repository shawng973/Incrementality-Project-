import { clsx } from "clsx";

interface CardProps {
  children: React.ReactNode;
  className?: string;
}

export function Card({ children, className }: CardProps) {
  return (
    <div
      className={clsx(
        "rounded-lg border border-gray-200 bg-white shadow-sm",
        className
      )}
    >
      {children}
    </div>
  );
}

export function CardHeader({ children, className }: CardProps) {
  return (
    <div className={clsx("border-b border-gray-200 px-6 py-4", className)}>
      {children}
    </div>
  );
}

export function CardContent({ children, className }: CardProps) {
  return (
    <div className={clsx("px-6 py-4", className)}>{children}</div>
  );
}

export function CardFooter({ children, className }: CardProps) {
  return (
    <div
      className={clsx(
        "border-t border-gray-200 px-6 py-4 bg-gray-50 rounded-b-lg",
        className
      )}
    >
      {children}
    </div>
  );
}
