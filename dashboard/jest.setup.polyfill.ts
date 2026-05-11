import * as React from "react";

// Monkey-patch React.act for React 19 production builds.
// react-dom/test-utils uses require("react").act internally,
// and React 19 does not export `act` from production builds.
const reactActStub = (fn: () => unknown) => fn();

interface ReactWithAct {
  act: typeof reactActStub;
}

if (!(React as unknown as ReactWithAct).act) {
  (React as unknown as ReactWithAct).act = reactActStub;
}

// eslint-disable-next-line @typescript-eslint/no-require-imports
const reactCjs = require("react") as ReactWithAct;
if (!reactCjs.act) {
  reactCjs.act = reactActStub;
}

import { act } from "react-dom/test-utils";

// Replace stubs with real act from react-dom/test-utils
(React as unknown as ReactWithAct).act = act;
reactCjs.act = act;
