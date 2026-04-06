import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";

// ---------------------------------------------------------------------------
// Schema
// ---------------------------------------------------------------------------

export const step2Schema = z
  .object({
    start_date: z.string().optional(),
    end_date: z.string().optional(),
    cooldown_weeks: z.coerce
      .number()
      .int()
      .min(0, "Cannot be negative")
      .max(8, "Maximum 8 cooldown weeks")
      .optional()
      .or(z.literal("")),
  })
  .refine(
    (data) => {
      if (data.start_date && data.end_date) {
        return new Date(data.end_date) > new Date(data.start_date);
      }
      return true;
    },
    {
      message: "End date must be after start date",
      path: ["end_date"],
    }
  );

export type Step2Data = z.infer<typeof step2Schema>;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface Step2DatesProps {
  defaultValues?: Partial<Step2Data>;
  onBack: () => void;
  onNext: (data: Step2Data) => void;
}

export function Step2Dates({ defaultValues, onBack, onNext }: Step2DatesProps) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<Step2Data>({
    resolver: zodResolver(step2Schema),
    defaultValues: {
      start_date: "",
      end_date: "",
      cooldown_weeks: undefined,
      ...defaultValues,
    },
  });

  return (
    <form onSubmit={handleSubmit(onNext)} noValidate>
      <p className="mb-5 text-sm text-gray-500">
        Dates are optional — you can set or update them later. Leave blank to save as draft and
        configure when the test launches.
      </p>

      <div className="space-y-5">
        {/* Start date */}
        <div>
          <label
            htmlFor="start_date"
            className="mb-1 block text-sm font-medium text-gray-700"
          >
            Test start date
          </label>
          <input
            id="start_date"
            type="date"
            {...register("start_date")}
            className="w-48 rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
        </div>

        {/* End date */}
        <div>
          <label
            htmlFor="end_date"
            className="mb-1 block text-sm font-medium text-gray-700"
          >
            Test end date
          </label>
          <input
            id="end_date"
            type="date"
            {...register("end_date")}
            className="w-48 rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
          {errors.end_date && (
            <p role="alert" className="mt-1 text-xs text-red-600">
              {errors.end_date.message}
            </p>
          )}
        </div>

        {/* Cooldown weeks */}
        <div>
          <label
            htmlFor="cooldown_weeks"
            className="mb-1 block text-sm font-medium text-gray-700"
          >
            Cooldown period (weeks)
          </label>
          <input
            id="cooldown_weeks"
            type="number"
            min={0}
            max={8}
            placeholder="0"
            {...register("cooldown_weeks")}
            className="w-24 rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
          <p className="mt-1 text-xs text-gray-400">
            Weeks after the test ends before analysing results (accounts for attribution lag).
          </p>
          {errors.cooldown_weeks && (
            <p role="alert" className="mt-1 text-xs text-red-600">
              {errors.cooldown_weeks.message}
            </p>
          )}
        </div>
      </div>

      <div className="mt-8 flex justify-between">
        <Button type="button" variant="secondary" onClick={onBack}>
          ← Back
        </Button>
        <Button type="submit">
          Next: Review →
        </Button>
      </div>
    </form>
  );
}
