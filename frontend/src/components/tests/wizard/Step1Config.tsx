import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";

// ---------------------------------------------------------------------------
// Schema
// ---------------------------------------------------------------------------

export const step1Schema = z.object({
  name: z.string().min(1, "Test name is required").max(120, "Name must be 120 characters or fewer"),
  description: z.string().max(500, "Description must be 500 characters or fewer").optional(),
  test_type: z.enum(["geo_split", "pre_post"]),
  channel: z.string().optional(),
  region_granularity: z.enum(["state", "dma", "zip"]),
  n_cells: z.coerce.number().int().min(2, "Minimum 2 cells").max(4, "Maximum 4 cells"),
});

export type Step1Data = z.infer<typeof step1Schema>;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const CHANNELS = [
  { value: "ctv", label: "CTV" },
  { value: "paid_search", label: "Paid Search" },
  { value: "paid_social", label: "Paid Social" },
  { value: "display", label: "Display" },
  { value: "audio", label: "Audio" },
  { value: "ooh", label: "OOH" },
  { value: "other", label: "Other" },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface Step1ConfigProps {
  defaultValues?: Partial<Step1Data>;
  onNext: (data: Step1Data) => void;
}

export function Step1Config({ defaultValues, onNext }: Step1ConfigProps) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<Step1Data>({
    resolver: zodResolver(step1Schema),
    defaultValues: {
      test_type: "geo_split",
      region_granularity: "state",
      n_cells: 2,
      ...defaultValues,
    },
  });

  return (
    <form onSubmit={handleSubmit(onNext)} noValidate>
      <div className="space-y-5">
        {/* Test name */}
        <div>
          <label htmlFor="name" className="mb-1 block text-sm font-medium text-gray-700">
            Test name <span className="text-red-500">*</span>
          </label>
          <input
            id="name"
            type="text"
            placeholder="Q1 CTV Incremental Test"
            {...register("name")}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
          {errors.name && (
            <p role="alert" className="mt-1 text-xs text-red-600">
              {errors.name.message}
            </p>
          )}
        </div>

        {/* Description */}
        <div>
          <label htmlFor="description" className="mb-1 block text-sm font-medium text-gray-700">
            Description <span className="text-gray-400">(optional)</span>
          </label>
          <textarea
            id="description"
            rows={2}
            placeholder="Brief context about this test…"
            {...register("description")}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
          {errors.description && (
            <p role="alert" className="mt-1 text-xs text-red-600">
              {errors.description.message}
            </p>
          )}
        </div>

        {/* Test type */}
        <fieldset>
          <legend className="mb-2 text-sm font-medium text-gray-700">
            Test type <span className="text-red-500">*</span>
          </legend>
          <div className="flex gap-4">
            {(
              [
                { value: "geo_split", label: "Geo Split", desc: "K-means clustering, randomized geo assignment" },
                { value: "pre_post", label: "Pre / Post", desc: "Single market, before-and-after comparison" },
              ] as const
            ).map((opt) => (
              <label
                key={opt.value}
                className="flex flex-1 cursor-pointer items-start gap-3 rounded-md border border-gray-200 p-3 hover:border-brand-300"
              >
                <input
                  type="radio"
                  value={opt.value}
                  {...register("test_type")}
                  className="mt-0.5 accent-brand-600"
                />
                <div>
                  <div className="text-sm font-medium text-gray-900">{opt.label}</div>
                  <div className="text-xs text-gray-500">{opt.desc}</div>
                </div>
              </label>
            ))}
          </div>
        </fieldset>

        {/* Channel */}
        <div>
          <label htmlFor="channel" className="mb-1 block text-sm font-medium text-gray-700">
            Channel <span className="text-gray-400">(optional)</span>
          </label>
          <select
            id="channel"
            {...register("channel")}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          >
            <option value="">Select a channel…</option>
            {CHANNELS.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </div>

        {/* Region granularity */}
        <fieldset>
          <legend className="mb-2 text-sm font-medium text-gray-700">
            Region granularity <span className="text-red-500">*</span>
          </legend>
          <div className="flex gap-3">
            {(["state", "dma", "zip"] as const).map((g) => (
              <label key={g} className="flex cursor-pointer items-center gap-2">
                <input
                  type="radio"
                  value={g}
                  {...register("region_granularity")}
                  className="accent-brand-600"
                />
                <span className="text-sm text-gray-700 capitalize">{g.toUpperCase()}</span>
              </label>
            ))}
          </div>
        </fieldset>

        {/* Number of cells */}
        <div>
          <label htmlFor="n_cells" className="mb-1 block text-sm font-medium text-gray-700">
            Number of test cells <span className="text-red-500">*</span>
          </label>
          <select
            id="n_cells"
            {...register("n_cells")}
            className="w-48 rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          >
            <option value={2}>2 cells (treatment + control)</option>
            <option value={3}>3 cells</option>
            <option value={4}>4 cells</option>
          </select>
          {errors.n_cells && (
            <p role="alert" className="mt-1 text-xs text-red-600">
              {errors.n_cells.message}
            </p>
          )}
        </div>
      </div>

      <div className="mt-8 flex justify-end">
        <Button type="submit">
          Next: Dates →
        </Button>
      </div>
    </form>
  );
}
