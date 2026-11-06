interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

let deferred: BeforeInstallPromptEvent | null = null

export function initInstallButton(btnId: string, fallbackElId: string) {
  const btn = document.getElementById(btnId) as HTMLButtonElement | null
  const fallback = document.getElementById(fallbackElId)

  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault()
    deferred = e as BeforeInstallPromptEvent
    if (btn) {
      btn.textContent = 'Install app'
    }
  })

  window.addEventListener('appinstalled', () => {
    if (btn) {
      btn.textContent = 'Installed'
      btn.disabled = true
    }
    if (fallback) fallback.style.display = 'none'
  })

  if (btn) {
    btn.addEventListener('click', async () => {
      if (deferred) {
        await deferred.prompt()
        const choice = await deferred.userChoice
        deferred = null
        if (choice.outcome === 'accepted') {
          btn.textContent = 'Installing…'
          btn.disabled = true
          setTimeout(() => { btn.style.display = 'none' }, 2000)
        }
      } else {
        // No deferred prompt (Chrome usually fires it only after a user
        // interaction; capture the signal above). Show the manual steps.
        if (fallback) fallback.style.display = 'block'
        btn.textContent = 'See Chrome menu to install'
      }
    })
  }
}
