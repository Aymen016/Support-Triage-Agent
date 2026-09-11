import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";
import { TopBar } from "./components/TopBar";
import { ToastProvider } from "./components/ui/Toast";
import { Inbox } from "./pages/Inbox";
import { Runs } from "./pages/Runs";
import { Settings } from "./pages/Settings";

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <div className="flex h-screen overflow-hidden">
          <Sidebar />
          <div className="flex-1 flex flex-col min-w-0">
            <TopBar />
            <div className="flex-1 min-h-0">
              <Routes>
                <Route path="/" element={<Inbox />} />
                <Route path="/runs" element={<Runs />} />
                <Route path="/runs/:emailId" element={<Runs />} />
                <Route path="/settings" element={<Settings />} />
              </Routes>
            </div>
          </div>
        </div>
      </ToastProvider>
    </BrowserRouter>
  );
}
