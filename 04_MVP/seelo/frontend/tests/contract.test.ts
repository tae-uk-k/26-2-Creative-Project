import { expect, it, vi } from "vitest";
import payloads from "./fixtures/requests.json";
import { ApiClient } from "../src/api/client";
import { createDemoGateway } from "../src/commerce/demo-gateway";
import { createHttpGateway } from "../src/commerce/http-gateway";
import {
  factInputSchema,
  generateSchema,
  fieldSchema,
} from "../src/commerce/schemas";

it("실제 백엔드에 맞춘 요청 본문을 전송한다", async () => {
  const demo = createDemoGateway();
  const store = (await demo.stores())[0];
  const product = (await demo.products(store.id, { page: 1, query: "" }))
    .items[0];
  const workspace = await demo.command(store.id, product.id, {
    action: "generate",
    fields: ["description"],
    requiredFacts: [],
    useAi: false,
    allowEditorConversion: false,
  });
  const plan = workspace.plans[0];
  const fetcher = vi
    .fn<typeof fetch>()
    .mockImplementation(async (path, init) => {
      const url = String(path);
      let data: unknown;
      if (init?.method === "POST")
        data = /\/(research|facts|answers|import|manual-snapshot)$/.test(url)
          ? product
          : plan;
      else if (url.endsWith("/writes")) data = { writes: [] };
      else if (url.endsWith("/plans")) data = { plans: [plan] };
      else data = url.includes("/products/") ? product : store;
      return new Response(JSON.stringify(data), { status: 200 });
    });
  const gateway = createHttpGateway(
    new ApiClient({ fetch: fetcher, cookie: () => "seelo_csrf=token" }),
  );
  await gateway.command(store.id, product.id, {
    action: "facts",
    facts: payloads.FactsInput.facts.map((fact) => factInputSchema.parse(fact)),
  });
  await gateway.command(store.id, product.id, {
    action: "research",
    ...payloads.ResearchInput,
  });
  await gateway.command(store.id, product.id, {
    action: "answers",
    answers: payloads.AnswerInput.answers,
  });
  await gateway.command(store.id, product.id, {
    action: "generate",
    ...generateSchema.parse(payloads.PlanCreate),
  });
  await gateway.command(store.id, product.id, {
    action: "approve",
    planId: plan.id,
    ...payloads.PlanApprove,
    fields: payloads.PlanApprove.fields.map((field) =>
      fieldSchema.parse(field),
    ),
  });
  await gateway.command(store.id, product.id, {
    action: "publication",
    planId: plan.id,
    ...payloads.PublicationCheck,
  });
  await gateway.command(store.id, product.id, {
    action: "manual-result",
    planId: plan.id,
    ...payloads.ManualResult,
  });
  const bodies = fetcher.mock.calls
    .filter(([, init]) => init?.method === "POST")
    .map(([, init]) => JSON.parse(init!.body as string));
  expect(bodies).toEqual([
    payloads.FactsInput,
    payloads.ResearchInput,
    payloads.AnswerInput,
    payloads.PlanCreate,
    payloads.PlanApprove,
    payloads.PublicationCheck,
    payloads.ManualResult,
  ]);
  expect(
    fetcher.mock.calls.filter(
      ([url, init]) =>
        String(url).endsWith("/approve") && init?.method === "POST",
    )[0][0],
  ).toBe(`/api/commerce/plans/${plan.id}/approve`);
});
