import { getStoredUser } from "@/lib/auth";

export function AccountPage() {
  const user = getStoredUser();
  return (
    <div className="max-w-lg rounded-xl border border-slate-200 bg-white p-5">
      <h1 className="text-xl font-bold">账号</h1>
      <dl className="mt-4 space-y-2 text-sm">
        <div className="flex justify-between gap-4">
          <dt className="text-slate-500">用户名</dt>
          <dd className="font-medium">{user?.username}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt className="text-slate-500">显示名</dt>
          <dd className="font-medium">{user?.display_name || "—"}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt className="text-slate-500">角色</dt>
          <dd className="font-medium">{user?.role}</dd>
        </div>
      </dl>
      <a
        href="/"
        className="mt-6 inline-block text-sm text-sky-700 hover:underline"
      >
        返回 SVQuant 主站
      </a>
    </div>
  );
}
