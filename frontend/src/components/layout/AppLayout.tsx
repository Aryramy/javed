import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import { Header } from '@/components/layout/Header'
import { Sidebar } from '@/components/layout/Sidebar'

export const AppLayout = () => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  return (
    <div className="min-h-screen flex flex-col bg-background text-foreground antialiased selection:bg-primary/20 selection:text-primary">
      <Header
        mobileMenuOpen={mobileMenuOpen}
        setMobileMenuOpen={setMobileMenuOpen}
      />
      <div className="flex-1 flex overflow-hidden">
        <Sidebar
          mobileOpen={mobileMenuOpen}
          setMobileOpen={setMobileMenuOpen}
        />
        <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8 bg-background/50">
          <div className="max-w-6xl mx-auto">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
