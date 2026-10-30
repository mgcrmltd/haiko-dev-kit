/**
 * Preview: runs each slot of the plugin against mock data in Expo Go, with no
 * Haiko app or runtime API. Not part of the plugin package.
 */
import React, { useCallback, useMemo, useRef, useState } from "react";
import { SafeAreaView, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { StatusBar } from "expo-status-bar";
import { MockHaikoHost } from "@mgcrm-haiko-builds/plugin-sdk";
import { MyField, MyScreen, MyStep, MyWidget } from "../src";
import { makeHost } from "./mockData";

const SLOTS = ["Screen", "Widget", "Field", "Step"] as const;
type Slot = (typeof SLOTS)[number];

export default function App() {
  const host = useMemo(makeHost, []);
  const [slot, setSlot] = useState<Slot>("Screen");
  return (
    <MockHaikoHost host={host}>
      <SafeAreaView style={styles.app}>
        <StatusBar style="dark" />
        <View style={styles.tabs} accessibilityRole="tablist">
          {SLOTS.map((s) => (
            <TouchableOpacity
              key={s}
              accessibilityRole="tab"
              accessibilityLabel={s}
              accessibilityHint={`Double tap to preview the ${s.toLowerCase()} slot`}
              accessibilityState={{ selected: s === slot }}
              onPress={() => setSlot(s)}
              style={[styles.tab, s === slot && styles.tabSelected]}
            >
              <Text style={s === slot ? styles.tabTextSelected : undefined}>{s}</Text>
            </TouchableOpacity>
          ))}
        </View>
        {slot === "Screen" && <MyScreen config={{ heading: "My open cases" }} />}
        {slot === "Widget" && <MyWidget config={{ screenId: "cases" }} openScreen={(id) => host.navigation.openScreen(id)} />}
        {slot === "Field" && <FieldHarness />}
        {slot === "Step" && <StepHarness />}
        <Log calls={host.log.length} />
      </SafeAreaView>
    </MockHaikoHost>
  );
}

/** A stand-in for the Haiko form: label, required marker and error are the form's. */
function FieldHarness() {
  const [value, setValue] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
  const error = touched && !value ? "Reference is required" : undefined;
  return (
    <ScrollView contentContainerStyle={styles.page}>
      <Text style={styles.label}>Reference <Text style={styles.required}>*</Text></Text>
      <MyField
        config={{}}
        value={value}
        onChange={(v) => { setValue(v); setTouched(true); }}
        onBlur={() => setTouched(true)}
        label="Reference"
        required
        disabled={false}
        error={error}
        reportError={() => {}}
      />
      {error && <Text accessibilityRole="alert" accessibilityLiveRegion="assertive" style={styles.error}>{error}</Text>}
      <Text>Form value: {JSON.stringify(value)}</Text>
    </ScrollView>
  );
}

/**
 * A stand-in for the Haiko wizard: Next runs the step's validator. Like the real
 * wizard, registerValidate and setValues keep their identity across renders; a
 * step registers in an effect that depends on registerValidate.
 */
function StepHarness() {
  const [values, setValuesState] = useState<Record<string, unknown>>({});
  const validator = useRef<(() => unknown) | null>(null);
  const [result, setResult] = useState<string>("");
  const registerValidate = useCallback((fn: () => unknown) => {
    validator.current = fn;
  }, []);
  const setValues = useCallback((patch: Record<string, unknown>) => setValuesState((v) => ({ ...v, ...patch })), []);
  return (
    <ScrollView contentContainerStyle={styles.page}>
      <Text accessibilityRole="header" style={styles.label}>Confirm</Text>
      <MyStep
        config={{}}
        values={values}
        setValues={setValues}
        registerValidate={registerValidate}
      />
      <TouchableOpacity
        accessibilityRole="button"
        accessibilityLabel="Next"
        accessibilityHint="Double tap to run the step's check"
        onPress={async () => {
          const r = validator.current ? await validator.current() : true;
          setResult(r === true ? "Next allowed" : String(r));
        }}
        style={styles.next}
      >
        <Text style={styles.nextText}>Next</Text>
      </TouchableOpacity>
      {result ? <Text accessibilityLiveRegion="polite">{result}</Text> : null}
    </ScrollView>
  );
}

function Log({ calls }: { calls: number }) {
  return <Text style={styles.log}>{`${calls} mock host call(s) so far`}</Text>;
}

const styles = StyleSheet.create({
  app: { flex: 1, backgroundColor: "#F9FAFB" },
  tabs: { flexDirection: "row", padding: 8, gap: 8 },
  tab: { flex: 1, minHeight: 48, justifyContent: "center", alignItems: "center", borderRadius: 8, borderWidth: 1, borderColor: "#9CA3AF" },
  tabSelected: { backgroundColor: "#1E40AF", borderColor: "#1E40AF" },
  tabTextSelected: { color: "#FFFFFF", fontWeight: "600" },
  page: { padding: 16, gap: 12 },
  label: { fontSize: 16, fontWeight: "600", color: "#111827" },
  required: { color: "#DC2626" },
  error: { color: "#DC2626" },
  next: { minHeight: 48, justifyContent: "center", alignItems: "center", borderRadius: 8, backgroundColor: "#1E40AF" },
  nextText: { color: "#FFFFFF", fontWeight: "600" },
  log: { padding: 8, color: "#6B7280", textAlign: "center" },
});
