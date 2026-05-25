/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState } from 'react';
import { 
  LayoutDashboard, 
  ClipboardList, 
  Wrench, 
  HelpCircle, 
  Search, 
  Plus, 
  ChevronRight, 
  Users, 
  Layers, 
  Square, 
  Spline, 
  Grid3X3, 
  Crosshair, 
  FileText,
  FileEdit,
  ArrowUpRight,
  Database,
  CheckCircle,
  X
} from 'lucide-react';
import { AnnotationFeature, Project, Collaborator } from '../types';
import { motion, AnimatePresence } from 'motion/react';

interface DashboardProps {
  projects: Project[];
  collaborators: Collaborator[];
  onCreateProject: (project: Omit<Project, 'id' | 'images'>) => void;
  onSelectProject: (project: Project) => void;
  onOpenAnnotationFeature: (feature: AnnotationFeature) => void;
  stats: {
    totalImages: number;
    totalAnnotations: string;
    activeCollaborators: number;
  };
}

export default function Dashboard({
  projects,
  collaborators,
  onCreateProject,
  onSelectProject,
  onOpenAnnotationFeature,
  stats
}: DashboardProps) {
  const [isNewProjectModalOpen, setIsNewProjectModalOpen] = useState(false);
  const [isCollaboratorsOpen, setIsCollaboratorsOpen] = useState(false);
  const [isEnterpriseModalOpen, setIsEnterpriseModalOpen] = useState(false);
  
  // New Project Form state
  const [newProjName, setNewProjName] = useState('');
  const [newProjDesc, setNewProjDesc] = useState('');
  const [newProjType, setNewProjType] = useState<'CV' | 'Multimodal' | 'Keypoints' | 'NLP'>('CV');
  const [newProjCategory, setNewProjCategory] = useState('Layout Analysis');
  
  // Filter search
  const [searchTerm, setSearchTerm] = useState('');

  const filteredProjects = projects.filter(p => 
    p.name.toLowerCase().includes(searchTerm.toLowerCase()) || 
    p.category.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const annotationFeatures: Array<{
    id: AnnotationFeature;
    label: string;
    status: 'online' | 'coming_soon';
    icon: React.ReactNode;
  }> = [
    { id: 'bounding_box', label: 'Bounding Box', status: 'coming_soon', icon: <Square className="w-4 h-4" /> },
    { id: 'polygon', label: 'Polygon Segment', status: 'coming_soon', icon: <Spline className="w-4 h-4" /> },
    { id: 'layout', label: 'Layout Analysis', status: 'online', icon: <Grid3X3 className="w-4 h-4" /> },
    { id: 'keypoints', label: 'Keypoints Picker', status: 'coming_soon', icon: <Crosshair className="w-4 h-4" /> },
    { id: 'text_transcription', label: 'Text Transcription', status: 'coming_soon', icon: <FileEdit className="w-4 h-4" /> },
  ];

  const handleCreateSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjName.trim()) return;

    onCreateProject({
      name: newProjName,
      description: newProjDesc || 'Custom document analysis dataset labeling project.',
      type: newProjType,
      progress: 0,
      thumbnail: 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=500&q=80',
      totalImages: 1,
      totalAnnotations: 0,
      category: newProjCategory,
    });

    // Reset fields
    setNewProjName('');
    setNewProjDesc('');
    setNewProjType('CV');
    setNewProjCategory('Layout Analysis');
    setIsNewProjectModalOpen(false);
  };

  return (
    <div id="markhub-dashboard" className="flex flex-1 overflow-hidden relative bg-[#0c0c0c] text-[#e5e5e5]">
      
      {/* Sidebar (SideNavBar) */}
      <aside className="w-20 bg-[#0e0e0e] border-r border-white/10 flex flex-col items-center py-10 space-y-12 h-full select-none z-10">
        <div 
          className="p-3 text-white bg-white/10 border border-white/5 rounded-none transition-all active:scale-95 cursor-pointer hover:bg-white/15"
          title="Dashboard"
        >
          <LayoutDashboard className="w-5 h-5" />
        </div>
        <div 
          onClick={() => setIsCollaboratorsOpen(true)}
          className="p-3 text-white/50 hover:bg-white/5 hover:text-white rounded-none border border-transparent hover:border-white/10 transition-all cursor-pointer"
          title="Team Members"
        >
          <Users className="w-5 h-5" />
        </div>
        <div
          className="p-3 text-white/50 hover:bg-white/5 hover:text-white rounded-none border border-transparent hover:border-white/10 transition-all cursor-pointer"
          title="Backend Dataset Records"
        >
          <Database className="w-5 h-5" />
        </div>
        <div 
          onClick={() => setIsEnterpriseModalOpen(true)}
          className="p-3 text-white/50 hover:bg-white/5 hover:text-white rounded-none border border-transparent hover:border-white/10 transition-all cursor-pointer"
          title="Enterprise Info"
        >
          <HelpCircle className="w-5 h-5" />
        </div>
      </aside>

      {/* Primary Area divided into left project content and right annotation panel */}
      <div className="flex-1 flex overflow-hidden">
        
        {/* Project Content list */}
        <section className="flex-1 overflow-y-auto custom-scrollbar px-12 py-12 space-y-12 bg-[#0c0c0c]">
          
          {/* Header Hero Section */}
          <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
            <div>
              <h1 className="font-serif italic text-4xl leading-tight text-white tracking-tight">
                Manage Your Data Pipeline and Annotation Projects
              </h1>
              <p className="text-white/60 text-sm font-serif italic max-w-2xl mt-3 leading-relaxed tracking-wider">
                Precision labeling tools for industrial AI datasets. Connect, annotate, and deploy layouts instantly.
              </p>
            </div>
          </div>

          {/* Search Row */}
          <div className="flex items-center gap-4 bg-white/[0.03] border border-white/10 px-4 py-2.5 rounded-none max-w-md focus-within:border-white/30 transition-all">
            <Search className="w-5 h-5 text-white/50" />
            <input 
              type="text" 
              placeholder="Search datasets or project tags..." 
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="flex-1 bg-transparent border-none outline-none text-xs text-white tracking-widest placeholder-white/20 uppercase"
            />
          </div>

          {/* KPI Dashboard Indicators */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div className="p-8 border border-white/5 rounded-none bg-[#141414] transition-all hover:bg-[#181818] hover:border-white/20 group select-none">
              <div className="flex justify-between items-center text-white/50">
                <span className="text-[10px] uppercase tracking-[0.3em] font-semibold">Total Pages</span>
                <span className="text-[9px] uppercase tracking-[0.2em] text-[#fa5252] opacity-0 group-hover:opacity-100 transition-opacity">Backend synced</span>
              </div>
              <div className="font-serif italic text-5xl mt-4 leading-none tracking-tight text-white">
                {stats.totalImages.toLocaleString()}
              </div>
            </div>

            <div 
              className="p-8 border border-white/5 rounded-none bg-[#141414] hover:bg-[#181818] transition-all"
            >
              <span className="text-white/50 text-[10px] uppercase tracking-[0.3em] font-semibold">Layout Blocks</span>
              <div className="font-serif italic text-5xl mt-4 leading-none tracking-tight text-white">
                {stats.totalAnnotations}
              </div>
            </div>

            <div className="p-8 border border-white/5 rounded-none bg-[#141414] hover:bg-[#181818] transition-all hover:border-white/20 group">
              <div className="flex justify-between items-center">
                <span className="text-white/50 text-[10px] uppercase tracking-[0.3em] font-semibold">Datasets</span>
                <span className="text-[9px] uppercase tracking-[0.2em] text-[#fa5252] opacity-0 group-hover:opacity-100 transition-opacity">Synced list</span>
              </div>
              <div className="font-serif italic text-5xl mt-4 leading-none tracking-tight text-white">
                {stats.activeCollaborators}
              </div>
            </div>
          </div>

          {/* Recent Projects List Grid */}
          <div className="space-y-6">
            <div className="flex justify-between items-center border-b border-white/5 pb-4">
              <h2 className="font-serif italic text-2xl text-white tracking-tight">Recent Projects</h2>
              <span className="text-[10px] uppercase tracking-[0.25em] text-white/40 bg-white/5 border border-white/10 px-3.5 py-1 font-semibold">
                {filteredProjects.length} Active Dataset{filteredProjects.length !== 1 ? 's' : ''}
              </span>
            </div>

            {filteredProjects.length === 0 ? (
              <div className="text-center py-20 border border-white/10 rounded-none bg-[#141414] px-6">
                <p className="text-white/60 text-sm italic font-serif">
                  {projects.length === 0 ? 'No backend datasets found. Run a PDF analysis first.' : 'No annotation projects matched your search.'}
                </p>
                <button 
                  onClick={() => setSearchTerm('')}
                  className="mt-4 text-[10px] text-white uppercase tracking-[0.2em] underline font-bold"
                >
                  Clear search filters
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                {filteredProjects.map((proj) => (
                  <div 
                    key={proj.id}
                    onClick={() => onSelectProject(proj)}
                    className="group bg-[#141414] border border-white/5 px-6 py-6 flex gap-6 cursor-pointer hover:bg-[#181818] hover:border-white/20 transition-all rounded-none relative"
                  >
                    {/* Project Image Panel */}
                    <div className="w-28 h-28 rounded-none bg-black overflow-hidden flex-shrink-0 border border-white/10 relative">
                      {proj.thumbnail ? (
                        <img
                          src={proj.thumbnail}
                          alt={`${proj.name} first analyzed page`}
                          referrerPolicy="no-referrer"
                          className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-700"
                        />
                      ) : (
                        <div className="flex h-full w-full items-center justify-center bg-white/[0.03] text-white/35">
                          <FileText className="h-9 w-9" />
                        </div>
                      )}
                      <div className="absolute inset-0 bg-black/45 group-hover:bg-black/10 duration-500" />
                    </div>

                    {/* Project text details */}
                    <div className="flex-1 flex flex-col justify-between">
                      <div>
                        <div className="flex justify-between items-center">
                          <span className="px-2 py-0.5 bg-white/10 border border-white/10 text-[9px] font-mono tracking-wider text-white/80">
                            {proj.type}
                          </span>
                          <span className="text-[10px] text-white/40 uppercase tracking-[0.15em] font-semibold">
                            {proj.category}
                          </span>
                        </div>
                        <h3 className="font-serif italic text-lg mt-2.5 text-white group-hover:text-white/80 transition-colors leading-tight line-clamp-1">
                          {proj.name}
                        </h3>
                        <p className="text-xs text-white/50 mt-1.5 leading-relaxed line-clamp-1">
                          {proj.description}
                        </p>
                      </div>

                      {/* Progress Metrics bar */}
                      <div className="space-y-2 mt-3">
                        <div className="flex justify-between text-[10px] uppercase tracking-[0.15em] text-white/40 font-semibold">
                          <span>Completion Progress</span>
                          <span className="font-mono text-white/80">{proj.progress}%</span>
                        </div>
                        <div className="w-full h-1 bg-white/5 rounded-none overflow-hidden">
                          <div 
                            className="h-full bg-white transition-all duration-700"
                            style={{ width: `${proj.progress}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>

        {/* Right Sidebar: Quick Tools panel */}
        <aside className="w-80 border-l border-white/10 bg-[#0e0e0e] p-8 flex flex-col gap-8 hidden xl:flex z-10 select-none">
          
          {/* Annotation types list */}
          <div>
            <h3 className="text-[10px] font-bold uppercase tracking-[0.25em] text-white/40 mb-6 font-sans">
              Supported Annotation Types
            </h3>
            <ul className="space-y-4">
              {annotationFeatures.map((feature) => (
                <li key={feature.id}>
                  <button
                    type="button"
                    onClick={() => onOpenAnnotationFeature(feature.id)}
                    className="group flex w-full items-center gap-4 border-b border-white/5 py-3 text-left transition-all hover:border-white/15 active:scale-[0.99]"
                  >
                    <span className={`${feature.status === 'online' ? 'text-white/65 group-hover:text-white' : 'text-white/35 group-hover:text-white/70'}`}>
                      {feature.icon}
                    </span>
                    <span className="flex-1 text-[11px] uppercase tracking-[0.18em] font-semibold text-white/70 group-hover:text-white">
                      {feature.label}
                    </span>
                    <span className={`text-[8px] uppercase tracking-[0.16em] font-mono ${feature.status === 'online' ? 'text-emerald-300' : 'text-white/30'}`}>
                      {feature.status === 'online' ? 'Live' : 'Soon'}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>

          {/* Call-to-Action module card */}
          <div className="mt-auto p-6 bg-[#141414] border border-white/5 text-white rounded-none relative overflow-hidden group">
            <div className="absolute inset-0 bg-gradient-to-br from-white/[0.03] to-transparent opacity-60" />
            <div className="relative z-10 flex flex-col h-full">
              <h4 className="font-serif italic text-lg text-white">Upgrade to Enterprise</h4>
              <p className="text-white/50 text-xs mt-2.5 leading-relaxed">
                Unlock advanced layout model validation, active learning cycles, and secure SSO team mappings.
              </p>
              <button 
                onClick={() => setIsEnterpriseModalOpen(true)}
                className="mt-5 bg-white text-black hover:bg-white/90 w-full py-2.5 rounded-none font-bold text-[10px] tracking-[0.2em] uppercase transition-all duration-150"
              >
                Learn More
              </button>
            </div>
          </div>
        </aside>
      </div>

      {/* Footer bar containing fast navigators */}
      <footer className="absolute bottom-0 left-0 w-full flex flex-col md:flex-row justify-between items-center px-10 py-6 border-t border-white/10 bg-[#0c0c0c]/95 backdrop-blur-md z-10 select-none">
        <div className="flex gap-8 text-[9px] uppercase tracking-[0.3em] text-white/40 font-mono">
          <a className="hover:text-white transition-colors flex items-center gap-2" href="#annotations">
            <span className="w-1.5 h-1.5 rounded-full bg-orange-700 animate-pulse" />
            <span>Vol. 012 / Issue 04</span>
          </a>
          <span className="opacity-30">© Studio Archaic MMXXVI</span>
        </div>
        <div className="flex gap-4 mt-3 md:mt-0">
          <button 
            onClick={() => {
              if (projects.length > 0) {
                onSelectProject(projects[0]);
              }
            }}
            className="px-5 py-2 border border-white/10 bg-[#141414] text-white/80 font-bold text-[10px] uppercase tracking-[0.2em] hover:bg-[#1a1a1a] hover:text-white rounded-none transition-colors duration-150"
          >
            Manage Active Workspace
          </button>
          <button 
            onClick={() => setIsNewProjectModalOpen(true)}
            className="px-5 py-2.5 bg-white text-black font-semibold text-[10px] uppercase tracking-[0.2em] hover:bg-white/95 transition-all duration-150 flex items-center gap-2 rounded-none"
          >
            <Plus className="w-4 h-4" /> Start New Annotation Project
          </button>
        </div>
      </footer>

      {/* dialog / modals */}
      <AnimatePresence>
        {isNewProjectModalOpen && (
          <div className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <motion.div 
              initial={{ scale: 0.98, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.98, opacity: 0 }}
              className="bg-[#0e0e0e] rounded-none p-8 max-w-lg w-full border border-white/10 shadow-2xl relative text-white"
            >
              <button 
                onClick={() => setIsNewProjectModalOpen(false)}
                className="absolute top-4 right-4 p-1 rounded-none hover:bg-white/5 text-white/40 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>

              <div className="flex items-center gap-3 mb-6">
                <Database className="w-6 h-6 text-white/80" />
                <h3 className="font-serif italic text-xl text-white">New Annotation Dataset</h3>
              </div>

              <form onSubmit={handleCreateSubmit} className="space-y-5">
                <div>
                  <label className="block text-[10px] font-semibold text-white/50 mb-1.5 uppercase tracking-[0.15em]">Project Name</label>
                  <input 
                    type="text" 
                    required
                    placeholder="e.g. Invoices Layout Parsing"
                    value={newProjName}
                    onChange={(e) => setNewProjName(e.target.value)}
                    className="w-full px-3.5 py-2.5 bg-white/[0.03] border border-white/10 rounded-none text-xs text-white focus:outline-none focus:border-white/30 transition-all uppercase tracking-wider placeholder-white/20"
                  />
                </div>

                <div>
                  <label className="block text-[10px] font-semibold text-white/50 mb-1.5 uppercase tracking-[0.15em]">Short Description</label>
                  <textarea 
                    placeholder="Describe datasets and annotation rules..."
                    value={newProjDesc}
                    onChange={(e) => setNewProjDesc(e.target.value)}
                    rows={3}
                    className="w-full px-3.5 py-2.5 bg-white/[0.03] border border-white/10 rounded-none text-xs text-white focus:outline-none focus:border-white/30 transition-all resize-none placeholder-white/20"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-[10px] font-semibold text-white/50 mb-1.5 uppercase tracking-[0.15em]">Model Type</label>
                    <select 
                      value={newProjType}
                      onChange={(e) => setNewProjType(e.target.value as any)}
                      className="w-full px-3.5 py-2.5 bg-[#0e0e0e] border border-white/10 rounded-none text-xs text-white focus:outline-none focus:border-white/30"
                    >
                      <option value="CV">Computer Vision (CV)</option>
                      <option value="Multimodal">Multimodal (VLM)</option>
                      <option value="Keypoints">Keypoints Tracking</option>
                      <option value="NLP">Text NLP / Parsing</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-[10px] font-semibold text-white/50 mb-1.5 uppercase tracking-[0.15em]">Classification Tag</label>
                    <select 
                      value={newProjCategory}
                      onChange={(e) => setNewProjCategory(e.target.value)}
                      className="w-full px-3.5 py-2.5 bg-[#0e0e0e] border border-white/10 rounded-none text-xs text-white focus:outline-none focus:border-white/30"
                    >
                      <option value="Layout Analysis">Layout Analysis</option>
                      <option value="Instance Segmentation">Instance Segmentation</option>
                      <option value="Image-Text Align">Image-Text Alignment</option>
                      <option value="Keypoints Detection">Keypoints Tracking</option>
                    </select>
                  </div>
                </div>

                <div className="pt-4 flex justify-end gap-3 border-t border-white/5">
                  <button 
                    type="button"
                    onClick={() => setIsNewProjectModalOpen(false)}
                    className="px-4 py-2 text-[10px] font-bold border border-white/10 hover:bg-white/5 rounded-none text-white/80 uppercase tracking-[0.15em]"
                  >
                    Cancel
                  </button>
                  <button 
                    type="submit"
                    className="px-5 py-2 bg-white text-black hover:bg-white/90 text-[10px] font-bold rounded-none uppercase tracking-[0.15em]"
                  >
                    Create Project
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}

        {isCollaboratorsOpen && (
          <div className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <motion.div 
              initial={{ scale: 0.98, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.98, opacity: 0 }}
              className="bg-[#0e0e0e] rounded-none p-8 max-w-md w-full border border-white/10 shadow-2xl relative text-white"
            >
              <button 
                onClick={() => setIsCollaboratorsOpen(false)}
                className="absolute top-4 right-4 p-1 rounded-none hover:bg-white/5 text-white/40"
              >
                <X className="w-5 h-5" />
              </button>

              <div className="flex items-center gap-3 mb-6">
                <Users className="w-6 h-6 text-white/85" />
                <h3 className="font-serif italic text-xl text-white">Active Team Collaborators</h3>
              </div>

              <div className="space-y-4 max-h-96 overflow-y-auto pr-2 custom-scrollbar">
                {collaborators.map(c => (
                  <div key={c.id} className="flex items-center justify-between p-3.5 bg-white/[0.02] rounded-none border border-white/5">
                    <div className="flex items-center gap-3">
                      <img 
                        src={c.avatar} 
                        alt="Avatar" 
                        referrerPolicy="no-referrer"
                        className="w-10 h-10 rounded-none object-cover border border-white/10"
                      />
                      <div>
                        <h4 className="text-xs font-bold text-white uppercase tracking-wider">{c.name}</h4>
                        <p className="text-[11px] text-white/40 mt-0.5">{c.role}</p>
                      </div>
                    </div>
                    <span className="flex items-center gap-1.5 text-[9px] uppercase tracking-wider bg-white/5 text-white/85 font-mono px-2 py-0.5 rounded-none border border-white/10">
                      <span className="w-1 h-1 bg-amber-500 rounded-full animate-pulse" /> Active
                    </span>
                  </div>
                ))}
              </div>

              <div className="mt-6 pt-4 border-t border-white/5 flex justify-end">
                <button 
                  onClick={() => setIsCollaboratorsOpen(false)}
                  className="px-5 py-2 bg-white text-black hover:bg-white/95 rounded-none text-[10px] font-bold uppercase tracking-[0.15em]"
                >
                  Close Panel
                </button>
              </div>
            </motion.div>
          </div>
        )}

        {isEnterpriseModalOpen && (
          <div className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <motion.div 
              initial={{ scale: 0.98, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.98, opacity: 0 }}
              className="bg-[#0e0e0e] rounded-none p-8 max-w-md w-full border border-white/10 shadow-2xl relative text-white"
            >
              <button 
                onClick={() => setIsEnterpriseModalOpen(false)}
                className="absolute top-4 right-4 p-1 rounded-none hover:bg-white/5 text-white/40"
              >
                <X className="w-5 h-5" />
              </button>

              <div className="flex items-center gap-3 mb-4">
                <ArrowUpRight className="w-6 h-6 text-white/80" />
                <h3 className="font-serif italic text-xl text-white">Enterprise Platform Info</h3>
              </div>

              <div className="space-y-4 text-xs text-white/60 font-sans leading-relaxed">
                <p>
                  MarkHub Enterprise provides full infrastructure scalability to orchestrate model labeling feedback loops for massive AI teams.
                </p>
                <div className="space-y-2.5 bg-white/[0.02] p-4 border border-white/5">
                  <div className="flex items-center gap-2 text-white/80 font-semibold">
                    <CheckCircle className="w-4 h-4 text-white/40" />
                    <span className="text-[11px] uppercase tracking-wider font-mono">Real-time Gemini Model Grounding</span>
                  </div>
                  <div className="flex items-center gap-2 text-white/80 font-semibold">
                    <CheckCircle className="w-4 h-4 text-white/40" />
                    <span className="text-[11px] uppercase tracking-wider font-mono">Single Sign-On (Active Directory / SSO)</span>
                  </div>
                  <div className="flex items-center gap-2 text-white/80 font-semibold">
                    <CheckCircle className="w-4 h-4 text-white/40" />
                    <span className="text-[11px] uppercase tracking-wider font-mono">High Quality SLA validation checks</span>
                  </div>
                </div>
                <p className="text-[11px] text-white/30 italic">
                  To proceed with upgrade license options details, consult with your DevOps or Billing accounts.
                </p>
              </div>

              <div className="mt-6 pt-4 border-t border-white/5 flex justify-end">
                <button 
                  onClick={() => setIsEnterpriseModalOpen(false)}
                  className="px-5 py-2 bg-white text-black hover:bg-white/95 rounded-none text-[10px] font-bold uppercase tracking-[0.15em]"
                >
                  Understood
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
