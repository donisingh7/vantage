import { DashboardOverview } from "@/components/DashboardOverview";
import { WorkspaceShell } from "@/components/WorkspaceShell";

export default function HomePage() {
  return <WorkspaceShell><DashboardOverview /></WorkspaceShell>;
}