import { lazy, Suspense, type ReactNode } from "react";
import { BrowserRouter, MemoryRouter, Navigate, Route, Routes, useParams } from "react-router-dom";
import type { Api } from "./api/api";
import { ApiProvider } from "./api/context";
import { Shell } from "./components/Shell";
import { Loading } from "./components/ui";
import { StatusProvider } from "./hooks/status";
import Home from "./screens/Home";

const NewEdit = lazy(() => import("./screens/NewEdit"));
const ProjectLayout = lazy(() => import("./screens/project/ProjectLayout"));
const Live = lazy(() => import("./screens/project/Live"));
const Review = lazy(() => import("./screens/project/Review"));
const Layers = lazy(() => import("./screens/project/Layers"));
const Revise = lazy(() => import("./screens/project/Revise"));
const Adjust = lazy(() => import("./screens/project/Adjust"));
const Deliver = lazy(() => import("./screens/project/Deliver"));
const Libraries = lazy(() => import("./screens/studio/Libraries"));
const Brands = lazy(() => import("./screens/studio/Brands"));
const Quality = lazy(() => import("./screens/studio/Quality"));
const Settings = lazy(() => import("./screens/studio/Settings"));

function ProjectIndex() {
  const { id } = useParams();
  return <Navigate to={`/p/${id}/live`} replace />;
}

export function AppRoutes() {
  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<Home />} />
          <Route path="new" element={<NewEdit />} />
          <Route path="p/:id" element={<ProjectLayout />}>
            <Route index element={<ProjectIndex />} />
            <Route path="live" element={<Live />} />
            <Route path="review" element={<Review />} />
            <Route path="layers" element={<Layers />} />
            <Route path="revise" element={<Revise />} />
            <Route path="adjust" element={<Adjust />} />
            <Route path="deliver" element={<Deliver />} />
          </Route>
          <Route path="studio/libraries" element={<Libraries />} />
          <Route path="studio/brands" element={<Brands />} />
          <Route path="studio/quality" element={<Quality />} />
          <Route path="studio/settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </Suspense>
  );
}

function Providers({ api, children }: { api?: Api; children: ReactNode }) {
  return (
    <ApiProvider api={api}>
      <StatusProvider>{children}</StatusProvider>
    </ApiProvider>
  );
}

export default function App() {
  return (
    <Providers>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </Providers>
  );
}

/** For tests: the whole app at a given URL with an injected API. */
export function TestApp({ api, path }: { api: Api; path: string }) {
  return (
    <Providers api={api}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </Providers>
  );
}
