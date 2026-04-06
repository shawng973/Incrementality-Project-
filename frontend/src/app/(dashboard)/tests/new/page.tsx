"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { WizardSteps } from "@/components/tests/wizard/WizardSteps";
import { Step1Config, type Step1Data } from "@/components/tests/wizard/Step1Config";
import { Step2Dates, type Step2Data } from "@/components/tests/wizard/Step2Dates";
import { Step3Review } from "@/components/tests/wizard/Step3Review";
import { api, ApiError } from "@/lib/api";

// ---------------------------------------------------------------------------
// Wizard steps config
// ---------------------------------------------------------------------------

const STEPS = [
  { index: 1, label: "Setup" },
  { index: 2, label: "Dates" },
  { index: 3, label: "Review" },
];

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function NewTestPage() {
  const router = useRouter();
  const [currentStep, setCurrentStep] = useState(0); // 0-based

  // Accumulated form data across steps
  const [step1Data, setStep1Data] = useState<Step1Data | null>(null);
  const [step2Data, setStep2Data] = useState<Step2Data | null>(null);

  // Submit state
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // Step handlers
  // ---------------------------------------------------------------------------

  function handleStep1Next(data: Step1Data) {
    setStep1Data(data);
    setCurrentStep(1);
  }

  function handleStep2Next(data: Step2Data) {
    setStep2Data(data);
    setCurrentStep(2);
  }

  async function handleCreate() {
    if (!step1Data || !step2Data) return;

    setIsSubmitting(true);
    setSubmitError(null);

    try {
      const payload = {
        name: step1Data.name,
        description: step1Data.description || undefined,
        test_type: step1Data.test_type,
        channel: step1Data.channel || undefined,
        region_granularity: step1Data.region_granularity,
        n_cells: step1Data.n_cells,
        start_date: step2Data.start_date || undefined,
        end_date: step2Data.end_date || undefined,
        cooldown_weeks:
          step2Data.cooldown_weeks != null && step2Data.cooldown_weeks !== ""
            ? Number(step2Data.cooldown_weeks)
            : undefined,
      };

      const test = await api.tests.create(payload);
      router.push(`/tests/${test.id}`);
    } catch (err) {
      if (err instanceof ApiError) {
        setSubmitError(
          err.status === 422
            ? "Some fields are invalid — please go back and check your input."
            : "Something went wrong creating your test. Please try again."
        );
      } else {
        setSubmitError("An unexpected error occurred. Please try again.");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div>
      {/* Back link */}
      <Link
        href="/tests"
        className="mb-6 inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700"
      >
        <ArrowLeft className="h-4 w-4" />
        Tests
      </Link>

      <h1 className="mb-6 text-2xl font-bold text-gray-900">New test</h1>

      <div className="mx-auto max-w-xl">
        <WizardSteps steps={STEPS} currentStep={currentStep} />

        <div className="rounded-lg border border-gray-200 bg-white p-8 shadow-sm">
          {currentStep === 0 && (
            <Step1Config
              defaultValues={step1Data ?? undefined}
              onNext={handleStep1Next}
            />
          )}

          {currentStep === 1 && (
            <Step2Dates
              defaultValues={step2Data ?? undefined}
              onBack={() => setCurrentStep(0)}
              onNext={handleStep2Next}
            />
          )}

          {currentStep === 2 && step1Data && step2Data && (
            <Step3Review
              step1={step1Data}
              step2={step2Data}
              isSubmitting={isSubmitting}
              error={submitError}
              onBack={() => setCurrentStep(1)}
              onSubmit={handleCreate}
            />
          )}
        </div>
      </div>
    </div>
  );
}
