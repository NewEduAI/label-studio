import { Button, Select, Userpic, EmptyState } from "@humansignal/ui";
import { IconMembers, IconPlus, IconTrash } from "@humansignal/icons";
import { useCallback, useContext, useEffect, useMemo, useState } from "react";
import { Spinner } from "../../components";
import { useAPI } from "../../providers/ApiProvider";
import { ProjectContext } from "../../providers/ProjectProvider";
import { cn } from "../../utils/bem";
import "./MembersSettings.prefix.css";

const PROJECT_ROLE_OPTIONS = [
  { value: "annotator", label: "Annotator" },
  { value: "reviewer", label: "Reviewer" },
];

export const MembersSettings = () => {
  const api = useAPI();
  const { project } = useContext(ProjectContext);

  const [members, setMembers] = useState([]);
  const [orgUsers, setOrgUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedUserId, setSelectedUserId] = useState(null);
  const [addRole, setAddRole] = useState("annotator");

  const fetchMembers = useCallback(async () => {
    if (!project?.id) return;
    setLoading(true);
    const response = await api.callApi("projectMembers", {
      params: { pk: project.id },
    });
    if (response?.results) {
      setMembers(response.results);
    } else if (Array.isArray(response)) {
      setMembers(response);
    }
    setLoading(false);
  }, [project?.id]);

  const fetchOrgUsers = useCallback(async () => {
    const response = await api.callApi("memberships", {
      params: { pk: 1, page_size: 1000 },
    });
    if (response?.results) {
      setOrgUsers(response.results);
    }
  }, []);

  useEffect(() => {
    fetchMembers();
    fetchOrgUsers();
  }, [fetchMembers, fetchOrgUsers]);

  const memberUserIds = useMemo(
    () => new Set(members.map((m) => m.user?.id)),
    [members],
  );

  const availableUsers = useMemo(
    () =>
      orgUsers
        .filter(({ user }) => !memberUserIds.has(user.id))
        .map(({ user }) => ({
          value: user.id,
          label: (
            <div className="flex items-center gap-2">
              <Userpic user={user} size={20} />
              <span>
                {user.first_name || user.last_name
                  ? `${user.first_name} ${user.last_name}`.trim()
                  : user.email}
              </span>
            </div>
          ),
        })),
    [orgUsers, memberUserIds],
  );

  const handleAddMember = useCallback(async () => {
    if (!selectedUserId) return;
    await api.callApi("addProjectMember", {
      params: { pk: project.id },
      body: { user_id: selectedUserId, role: addRole },
    });
    setSelectedUserId(null);
    fetchMembers();
  }, [selectedUserId, addRole, project?.id]);

  const handleRoleChange = useCallback(
    async (memberId, newRole) => {
      await api.callApi("updateProjectMember", {
        params: { pk: project.id, memberPk: memberId },
        body: { role: newRole },
      });
      fetchMembers();
    },
    [project?.id],
  );

  const handleRemove = useCallback(
    async (memberId) => {
      await api.callApi("removeProjectMember", {
        params: { pk: project.id, memberPk: memberId },
      });
      fetchMembers();
    },
    [project?.id],
  );

  return (
    <div className={cn("members-settings").toClassName()}>
      <div className={cn("members-settings").elem("wrapper").toClassName()}>
        <h1>Members</h1>
        <p className={cn("members-settings").elem("description").toClassName()}>
          Manage which users are members of this project. Project members can
          access tasks based on their role and the task distribution setting.
        </p>

        <div className={cn("members-settings").elem("add-section").toClassName()}>
          <div className={cn("members-settings").elem("add-row").toClassName()}>
            <div className={cn("members-settings").elem("add-user").toClassName()}>
              <Select
                options={availableUsers}
                value={selectedUserId}
                onChange={setSelectedUserId}
                placeholder="Select a user to add..."
                searchable
              />
            </div>
            <div className={cn("members-settings").elem("add-role").toClassName()}>
              <Select
                options={PROJECT_ROLE_OPTIONS}
                value={addRole}
                onChange={setAddRole}
              />
            </div>
            <Button
              variant="primary"
              look="filled"
              onClick={handleAddMember}
              disabled={!selectedUserId}
              leading={<IconPlus />}
            >
              Add
            </Button>
          </div>
        </div>

        <div className={cn("members-settings").elem("list-wrapper").toClassName()}>
          {loading ? (
            <div className={cn("members-settings").elem("loading").toClassName()}>
              <Spinner size={36} />
            </div>
          ) : members.length === 0 ? (
            <EmptyState
              icon={<IconMembers />}
              title="No members yet"
              description="Add organization members to this project so they can access and work on tasks."
            />
          ) : (
            <div className={cn("members-settings").elem("table").toClassName()}>
              <div className={cn("members-settings").elem("table-head").toClassName()}>
                <div className={cn("members-settings").elem("col").mix("avatar").toClassName()} />
                <div className={cn("members-settings").elem("col").mix("name").toClassName()}>
                  Name
                </div>
                <div className={cn("members-settings").elem("col").mix("email").toClassName()}>
                  Email
                </div>
                <div className={cn("members-settings").elem("col").mix("role").toClassName()}>
                  Role
                </div>
                <div className={cn("members-settings").elem("col").mix("actions").toClassName()} />
              </div>
              <div className={cn("members-settings").elem("table-body").toClassName()}>
                {members.map((member) => (
                  <div
                    key={member.id}
                    className={cn("members-settings").elem("row").toClassName()}
                  >
                    <div className={cn("members-settings").elem("cell").mix("avatar").toClassName()}>
                      <Userpic user={member.user} style={{ width: 28, height: 28 }} />
                    </div>
                    <div className={cn("members-settings").elem("cell").mix("name").toClassName()}>
                      {member.user.first_name} {member.user.last_name}
                    </div>
                    <div className={cn("members-settings").elem("cell").mix("email").toClassName()}>
                      {member.user.email}
                    </div>
                    <div
                      className={cn("members-settings").elem("cell").mix("role").toClassName()}
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Select
                        options={PROJECT_ROLE_OPTIONS}
                        value={member.role}
                        size="small"
                        onChange={(val) => handleRoleChange(member.id, val)}
                      />
                    </div>
                    <div className={cn("members-settings").elem("cell").mix("actions").toClassName()}>
                      <Button
                        variant="neutral"
                        look="outlined"
                        size="small"
                        onClick={() => handleRemove(member.id)}
                        leading={<IconTrash />}
                        aria-label="Remove member"
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

MembersSettings.title = "Members";
MembersSettings.path = "/members";
