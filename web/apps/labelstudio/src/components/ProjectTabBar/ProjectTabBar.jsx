import { useMemo } from "react";
import { NavLink } from "react-router-dom";
import { useProject } from "../../providers/ProjectProvider";
import { cn } from "../../utils/bem";
import "./ProjectTabBar.prefix.css";

const rootClass = cn("project-tab-bar");

const allTabs = [
  { path: "/dashboard", label: "Dashboard", managerOnly: true },
  { path: "/data", label: "Data Manager" },
  { path: "/settings", label: "Settings" },
];

export const ProjectTabBar = ({ children }) => {
  const { project } = useProject();
  const projectId = project?.id;
  const orgRole = window.APP_SETTINGS?.user?.organizationRole;
  const isAnnotator = orgRole === "annotator";

  const tabs = useMemo(() => {
    return allTabs.filter((tab) => !tab.managerOnly || !isAnnotator);
  }, [isAnnotator]);

  if (!projectId) return children;

  return (
    <>
      <div className={rootClass.elem("nav").toClassName()}>
        {tabs.map(({ path, label }) => (
          <NavLink
            key={path}
            to={`/projects/${projectId}${path}`}
            className={rootClass.elem("tab").toClassName()}
            activeClassName={rootClass.elem("tab").mod({ active: true }).toClassName()}
            data-external
          >
            {label}
          </NavLink>
        ))}
      </div>
      <div className={rootClass.elem("content").toClassName()}>
        {children}
      </div>
    </>
  );
};
