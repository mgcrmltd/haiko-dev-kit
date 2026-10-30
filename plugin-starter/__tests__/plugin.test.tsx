/**
 * Test your plugin against the mock host: no Haiko app, no API.
 * Run: npm test
 */
import React from "react";
import { fireEvent, render, screen } from "@testing-library/react-native";
import { MockHaikoHost, createMockHost, PluginError } from "@mgcrm-haiko-builds/plugin-sdk";
import { MyField, MyScreen, MyStep, MyWidget } from "../src";

const host = () =>
  createMockHost({
    tables: {
      incident: [
        { id: "1", title: "Leaking tap", statecode: 0 },
        { id: "2", title: "Fixed: fence", statecode: 1 },
      ],
    },
  });

test("MyScreen lists only open cases", async () => {
  render(<MockHaikoHost host={host()}><MyScreen config={{ heading: "Cases" }} /></MockHaikoHost>);
  expect(await screen.findByText("Leaking tap")).toBeTruthy();
  expect(screen.queryByText("Fixed: fence")).toBeNull();
});

test("MyScreen shows the CRM's message when loading fails", async () => {
  const failing = createMockHost({ tables: { incident: new PluginError("down", { userMessage: "Cases are unavailable today." }) } });
  render(<MockHaikoHost host={failing}><MyScreen config={{ heading: "Cases" }} /></MockHaikoHost>);
  expect(await screen.findByText("Cases are unavailable today.")).toBeTruthy();
});

test("MyWidget opens the configured screen", async () => {
  const openScreen = jest.fn();
  render(<MockHaikoHost host={host()}><MyWidget config={{ screenId: "cases" }} openScreen={openScreen} /></MockHaikoHost>);
  expect(await screen.findByText("1")).toBeTruthy();
  fireEvent.press(screen.getByLabelText("See all"));
  expect(openScreen).toHaveBeenCalledWith("cases");
});

test("MyField reports its value to the form", () => {
  const onChange = jest.fn();
  render(
    <MockHaikoHost host={host()}>
      <MyField config={{}} value={null} onChange={onChange} onBlur={() => {}} label="Reference" required disabled={false} reportError={() => {}} />
    </MockHaikoHost>
  );
  fireEvent.changeText(screen.getByLabelText("Reference, required"), "ABC-1");
  expect(onChange).toHaveBeenCalledWith("ABC-1");
});

test("MyStep blocks Next until confirmed", async () => {
  let validate: () => unknown = () => true;
  const { rerender } = render(
    <MockHaikoHost host={host()}>
      <MyStep config={{}} values={{}} setValues={() => {}} registerValidate={(fn) => (validate = fn)} />
    </MockHaikoHost>
  );
  expect(await validate()).toBe("Please confirm before continuing.");
  rerender(
    <MockHaikoHost host={host()}>
      <MyStep config={{}} values={{ my_agreed: true }} setValues={() => {}} registerValidate={(fn) => (validate = fn)} />
    </MockHaikoHost>
  );
  expect(await validate()).toBe(true);
});
