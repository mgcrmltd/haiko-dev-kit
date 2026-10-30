/**
 * Your plugin. Each export is one slot in haiko-plugin.json. Data only ever
 * comes through the SDK hooks; the app keeps it to the signed-in contact.
 */
import React, { useEffect, useState } from "react";
import { ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";
import {
  useQuery,
  useTheme,
  type FieldSlotProps,
  type ScreenSlotProps,
  type StepSlotProps,
  type WidgetSlotProps,
} from "@mgcrm-haiko-builds/plugin-sdk";

const FOCUS_RING = "#1A73E8";
const BORDER = "#9CA3AF";

/** Screen slot: the contact's open cases. Needs "incident" in data.read. */
export function MyScreen({ config }: ScreenSlotProps<{ heading: string }>) {
  const theme = useTheme();
  const { rows, loading, error } = useQuery({
    entity: "incident",
    columns: ["title"],
    where: [{ attribute: "statecode", operator: "eq", value: 0 }],
  });
  return (
    <ScrollView style={{ backgroundColor: theme.backgroundColor }} contentContainerStyle={styles.page}>
      <Text accessibilityRole="header" style={[styles.heading, { color: theme.textColor }]}>
        {config.heading}
      </Text>
      {loading && <Text accessibilityLiveRegion="polite">Loading…</Text>}
      {error && (
        <Text accessibilityRole="alert" accessibilityLiveRegion="assertive" style={{ color: theme.errorColor }}>
          {error.userMessage ?? "Something went wrong. Please try again."}
        </Text>
      )}
      {!loading && !error && rows.length === 0 && <Text style={{ color: theme.textColor }}>Nothing open.</Text>}
      {rows.map((r) => (
        <View key={r.id} style={[styles.card, { backgroundColor: theme.surfaceColor, borderRadius: theme.borderRadius }]}>
          <Text style={{ color: theme.textColor }}>{String(r.title)}</Text>
        </View>
      ))}
    </ScrollView>
  );
}

/** Widget slot: a dashboard card. */
export function MyWidget({ config, openScreen }: WidgetSlotProps<{ screenId?: string }>) {
  const theme = useTheme();
  const { rows } = useQuery({ entity: "incident", columns: ["title"], where: [{ attribute: "statecode", operator: "eq", value: 0 }] });
  return (
    <View style={[styles.card, { backgroundColor: theme.surfaceColor, borderRadius: theme.borderRadius }]}>
      <Text accessibilityRole="header" style={{ color: theme.textColor, fontWeight: "600" }}>Open cases</Text>
      <Text style={{ color: theme.textColor, fontSize: 28, fontWeight: "700" }}>{rows.length}</Text>
      {config.screenId ? (
        <Button label="See all" hint="Double tap to open your cases" onPress={() => openScreen(config.screenId!)} />
      ) : null}
    </View>
  );
}

/** Field slot: the form owns the label, required marker and error; render only the input. */
export function MyField({ value, onChange, label, required, disabled, error }: FieldSlotProps<string>) {
  const theme = useTheme();
  const [focused, setFocused] = useState(false);
  return (
    <TextInput
      accessibilityLabel={`${label}${required ? ", required" : ""}`}
      accessibilityHint={`Enter ${label.toLowerCase()}`}
      editable={!disabled}
      value={value ?? ""}
      onChangeText={(t) => onChange(t || null)}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      style={[
        styles.input,
        { color: theme.textColor, borderColor: focused ? FOCUS_RING : error ? theme.errorColor : BORDER, borderWidth: focused ? 2 : 1 },
      ]}
    />
  );
}

/** Step slot: Next is blocked until the validator returns true. */
export function MyStep({ values, setValues, registerValidate }: StepSlotProps) {
  const theme = useTheme();
  const agreed = values.my_agreed === true;
  useEffect(() => {
    registerValidate(() => (agreed ? true : "Please confirm before continuing."));
  }, [registerValidate, agreed]);
  return (
    <TouchableOpacity
      accessibilityRole="checkbox"
      accessibilityLabel="I confirm the details are correct"
      accessibilityHint="Double tap to confirm"
      accessibilityState={{ checked: agreed }}
      onPress={() => setValues({ my_agreed: !agreed })}
      style={[styles.button, { borderColor: agreed ? theme.primaryColor : BORDER }]}
    >
      <Text style={{ color: theme.textColor }}>{agreed ? "☑" : "☐"} I confirm the details are correct</Text>
    </TouchableOpacity>
  );
}

function Button({ label, hint, onPress }: { label: string; hint: string; onPress: () => void }) {
  const theme = useTheme();
  const [focused, setFocused] = useState(false);
  return (
    <TouchableOpacity
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={hint}
      onPress={onPress}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      style={[styles.button, { borderColor: focused ? FOCUS_RING : theme.primaryColor, borderWidth: focused ? 2 : 1 }]}
    >
      <Text style={{ color: theme.primaryColor, fontWeight: "600" }}>{label}</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  page: { padding: 16, gap: 12 },
  heading: { fontSize: 24, fontWeight: "700" },
  card: { padding: 16, gap: 4 },
  input: { minHeight: 48, borderRadius: 8, paddingHorizontal: 12, fontSize: 16 },
  button: { minHeight: 48, justifyContent: "center", alignItems: "center", borderRadius: 8, borderWidth: 1, paddingHorizontal: 16 },
});
