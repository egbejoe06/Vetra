import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { CodeFile, TechnicalProblemResponse } from '@/types'

export type LayoutMode = 'discussion' | 'coding'

export const useWorkspaceStore = defineStore('workspace', () => {
  const layoutMode = ref<LayoutMode>('discussion')
  const problemTitle = ref<string>('')
  const problemType = ref<string>('')
  const promptQuestion = ref<string>('')
  const instructions = ref<string>('')

  // Multi-file Code Editor Workspace (starts empty until problem is loaded)
  const files = ref<Record<string, string>>({})
  const activeFile = ref<string>('')

  const hasProblem = computed(() => {
    return Object.keys(files.value).length > 0 || !!problemTitle.value
  })

  const fileNames = computed<string[]>(() => Object.keys(files.value))

  const activeFileContent = computed<string>({
    get: () => (activeFile.value ? files.value[activeFile.value] || '' : ''),
    set: (val: string) => {
      if (activeFile.value) {
        files.value[activeFile.value] = val
      }
    },
  })

  const activeFileLanguage = computed<string>(() => {
    const file = activeFile.value.toLowerCase()
    if (file.endsWith('.py')) return 'python'
    if (file.endsWith('.ts')) return 'typescript'
    if (file.endsWith('.js')) return 'javascript'
    if (file.endsWith('.json')) return 'json'
    if (file.endsWith('.go')) return 'go'
    if (file.endsWith('.java')) return 'java'
    if (file.endsWith('.rs')) return 'rust'
    return 'plaintext'
  })

  function setLayoutMode(mode: LayoutMode) {
    layoutMode.value = mode
  }

  function toggleLayoutMode() {
    layoutMode.value = layoutMode.value === 'discussion' ? 'coding' : 'discussion'
  }

  function setActiveFile(fileName: string) {
    if (files.value[fileName] !== undefined) {
      activeFile.value = fileName
    }
  }

  function setFileContent(fileName: string, content: string) {
    files.value[fileName] = content
  }

  function addFile(fileName: string, initialContent = '') {
    files.value[fileName] = initialContent
    activeFile.value = fileName
  }

  function loadTechnicalProblem(prob: any, autoSwitch = false) {
    if (!prob) return
    problemTitle.value = prob.title || 'Technical Coding Challenge'
    promptQuestion.value = prob.prompt_question || prob.promptQuestion || ''
    instructions.value = prob.instructions || prob.context || prob.objective || ''
    if (prob.problem_type || prob.problemType) {
      problemType.value = prob.problem_type || prob.problemType
    }

    const rawFiles = prob.code_files || prob.codeFiles || []
    if (Array.isArray(rawFiles) && rawFiles.length > 0) {
      const newFiles: Record<string, string> = {}
      let firstFileName = ''

      for (const cf of rawFiles) {
        const filePath = cf.file_path || cf.path || cf.name || 'main.py'
        newFiles[filePath] = cf.content || ''
        if (!firstFileName) {
          firstFileName = filePath
        }
      }

      files.value = newFiles
      if (firstFileName) {
        activeFile.value = firstFileName
      }
    }

    // Switch to coding mode only if explicitly requested (e.g. interviewer presents problem)
    if (autoSwitch) {
      layoutMode.value = 'coding'
    }
  }

  function resetWorkspace() {
    files.value = {}
    activeFile.value = ''
    problemTitle.value = ''
    problemType.value = ''
    promptQuestion.value = ''
    instructions.value = ''
    layoutMode.value = 'discussion'
  }

  return {
    layoutMode,
    problemTitle,
    problemType,
    promptQuestion,
    instructions,
    files,
    activeFile,
    hasProblem,
    fileNames,
    activeFileContent,
    activeFileLanguage,
    setLayoutMode,
    toggleLayoutMode,
    setActiveFile,
    setFileContent,
    addFile,
    loadTechnicalProblem,
    resetWorkspace,
  }
})
