import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "pl.apka.companyresearchlab",
  appName: "Company Lab",
  webDir: "dist",

  server: {
    androidScheme: "http",
    cleartext: true,
  },
};

export default config;
