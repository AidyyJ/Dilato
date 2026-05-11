"use client";

import { Suspense } from "react";
import NewListingForm from "./NewListingForm";

export default function NewListingPage() {
  return (
    <Suspense fallback={<div className="text-sm text-neutral-500">Loading…</div>}>
      <NewListingForm />
    </Suspense>
  );
}
