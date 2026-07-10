import { forwardRef, useImperativeHandle, useRef } from 'react'

interface ImportLauncherProps {
  onFiles: (files: File[]) => void
}

export interface ImportLauncherHandle {
  open: () => void
}

/**
 * Renders a hidden <input type="file" multiple> and exposes an open() method via ref.
 * Call launcherRef.current?.open() to trigger the OS file picker.
 * When the user selects files, onFiles(files) is called and the input is reset
 * so the same files can be re-selected in subsequent clicks.
 * Cap enforcement (>12 warn, >24 block) is handled in ImportModal.
 */
const ImportLauncher = forwardRef<ImportLauncherHandle, ImportLauncherProps>(
  function ImportLauncher({ onFiles }, ref) {
    const inputRef = useRef<HTMLInputElement>(null)

    useImperativeHandle(ref, () => ({
      open() {
        inputRef.current?.click()
      },
    }))

    return (
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,application/pdf"
        multiple
        hidden
        aria-hidden="true"
        tabIndex={-1}
        onChange={e => {
          const files = Array.from(e.target.files ?? [])
          if (inputRef.current) inputRef.current.value = ''
          if (files.length > 0) onFiles(files)
        }}
      />
    )
  }
)

export default ImportLauncher
