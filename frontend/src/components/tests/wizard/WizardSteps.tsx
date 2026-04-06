import { clsx } from "clsx";
import { Check } from "lucide-react";

export interface Step {
  index: number;
  label: string;
}

interface WizardStepsProps {
  steps: Step[];
  currentStep: number; // 0-based
}

export function WizardSteps({ steps, currentStep }: WizardStepsProps) {
  return (
    <nav aria-label="Progress" className="mb-8">
      <ol className="flex items-center gap-0">
        {steps.map((step, i) => {
          const isDone = i < currentStep;
          const isActive = i === currentStep;
          const isLast = i === steps.length - 1;

          return (
            <li key={step.index} className="flex items-center">
              {/* Circle + label */}
              <div className="flex flex-col items-center">
                <div
                  aria-current={isActive ? "step" : undefined}
                  className={clsx(
                    "flex h-8 w-8 items-center justify-center rounded-full border-2 text-sm font-semibold transition-colors",
                    isDone &&
                      "border-brand-600 bg-brand-600 text-white",
                    isActive &&
                      "border-brand-600 bg-white text-brand-600",
                    !isDone && !isActive &&
                      "border-gray-300 bg-white text-gray-400"
                  )}
                >
                  {isDone ? (
                    <Check className="h-4 w-4" aria-hidden="true" />
                  ) : (
                    step.index
                  )}
                </div>
                <span
                  className={clsx(
                    "mt-1 text-xs font-medium",
                    isActive ? "text-brand-600" : "text-gray-500"
                  )}
                >
                  {step.label}
                </span>
              </div>

              {/* Connector line */}
              {!isLast && (
                <div
                  className={clsx(
                    "mx-2 mb-4 h-0.5 w-16 flex-shrink-0 transition-colors",
                    isDone ? "bg-brand-600" : "bg-gray-200"
                  )}
                />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
