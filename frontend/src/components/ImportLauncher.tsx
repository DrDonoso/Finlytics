import { forwardRef, useImperativeHandle, useRef } from 'react'

interface ImportLauncherProps {
  onFile: (file: File) => void
}

export interface ImportLauncherHandle {
  open: () => void
}

/**
 * Renders a hidden <input type="file"> and exposes an open() method via ref.
 * Call launcherRef.current?.open() to trigger the OS file picker directly.
 * When the user selects a file, onFile(file) is called and the input is reset
 * so the same file can be re-selected in subsequent clicks.
 */
const ImportLauncher = forwardRef<ImportLauncherHandle, ImportLauncherProps>(
  function ImportLauncher({ onFile }, ref) {
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
        hidden
        aria-hidden="true"
        tabIndex={-1}
        onChange={e => {
          const f = e.target.files?.[0]
          if (f) onFile(f)
          if (inputRef.current) inputRef.current.value = ''
        }}
      />
    )
  }
)

export default ImportLauncher
