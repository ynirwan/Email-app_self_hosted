export default function Topbar() {
  return (
    <header className="bg-white shadow px-6 py-4 flex items-center justify-between">
      <h1 className="text-lg font-semibold text-gray-700">Dashboard</h1>
      <div>
        <button className="bg-red-500 text-white px-4 py-1 rounded hover:bg-red-600">
          Logout
        </button>
      </div>
    </header>
  )
}

