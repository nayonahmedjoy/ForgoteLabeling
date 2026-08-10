import { useEffect, useState } from "react";

import Navbar from "../components/Navbar";
import ProjectCard from "../components/ProjectCard";
import CreateProjectModal from "../components/CreateProjectModal";
import {
  getProjects,
  createProject,
  deleteProject,
} from "../api/projectApi";

export default function Dashboard() {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showModal, setShowModal] = useState(false);

  useEffect(() => {
    loadProjects();
  }, []);

  async function loadProjects() {
    setLoading(true);
    setError("");
    try {
      const data = await getProjects();
      setProjects(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err.message || "Failed to load projects.");
    } finally {
      setLoading(false);
    }
  }

  async function handleCreate(name) {
    const project = await createProject(name);
    // Optimistically prepend, then refresh from server for accurate counts.
    setProjects((prev) => [project, ...prev]);
  }

  async function handleDelete(project) {
    if (!window.confirm(`Delete "${project.name}"? This cannot be undone.`)) {
      return;
    }
    try {
      await deleteProject(project.id);
      setProjects((prev) => prev.filter((p) => p.id !== project.id));
    } catch (err) {
      setError(err.message || "Failed to delete project.");
    }
  }

  return (
    <>
      <Navbar
        right={
          <button className="primary" onClick={() => setShowModal(true)}>
            + Create Project
          </button>
        }
      />

      <div className="page">
        <div className="row between">
          <h1>Projects</h1>
        </div>

        {loading ? (
          <div className="state">
            <span className="spin" /> Loading projects…
          </div>
        ) : error ? (
          <div className="state error">
            {error}
            <div style={{ marginTop: 12 }}>
              <button onClick={loadProjects}>Retry</button>
            </div>
          </div>
        ) : projects.length === 0 ? (
          <div className="state">
            <p>No projects yet.</p>
            <div style={{ marginTop: 12 }}>
              <button className="primary" onClick={() => setShowModal(true)}>
                Create your first project
              </button>
            </div>
          </div>
        ) : (
          <div className="project-grid">
            {projects.map((project) => (
              <ProjectCard
                key={project.id}
                project={project}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}
      </div>

      {showModal ? (
        <CreateProjectModal
          onClose={() => setShowModal(false)}
          onCreate={handleCreate}
        />
      ) : null}
    </>
  );
}
