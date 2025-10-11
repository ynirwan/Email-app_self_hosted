import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useNavigate } from "react-router-dom";
import API from "../api";

export default function SubscriberListView() {
    const { listName } = useParams();

    const [subscribers, setSubscribers] = useState([]);
    const [loading, setLoading] = useState(true);
    const [currentPage, setCurrentPage] = useState(1);
    const [totalPages, setTotalPages] = useState(1);
    const [totalCount, setTotalCount] = useState(0);
    const [searchTerm, setSearchTerm] = useState("");
    const [customFieldKeys, setCustomFieldKeys] = useState([]);
    

    // Edit modal state
    const [editModalOpen, setEditModalOpen] = useState(false);
    const [editSubscriber, setEditSubscriber] = useState(null);
    const [saving, setSaving] = useState(false);

    const ITEMS_PER_PAGE = 50;

    const navigate = useNavigate();

    const fetchSubscribers = async (page = 1, search = "") => {
        setLoading(true);
        try {
            const params = { page, limit: ITEMS_PER_PAGE };
            if (search) params.search = search;

            const response = await API.get(`/subscribers/list/${listName}`, { params });
            const data = response.data;

            if (data.success && data.subscribers) {
                setSubscribers(data.subscribers);
                setTotalPages(data.pagination?.total_pages || 1);
                setTotalCount(data.pagination?.total || 0);
                setCurrentPage(page);

                // Extract all unique custom field keys
                const keysSet = new Set();
                data.subscribers.forEach((sub) => {
                    if (sub.custom_fields) {
                        Object.keys(sub.custom_fields).forEach((key) => keysSet.add(key));
                    }
                });
                setCustomFieldKeys(Array.from(keysSet));
            } else {
                setSubscribers([]);
                setTotalPages(1);
                setTotalCount(0);
                setCustomFieldKeys([]);
            }
        } catch (e) {
            console.error("Fetch error:", e);
            alert("Failed to fetch subscribers");
            setSubscribers([]);
            setTotalPages(1);
            setTotalCount(0);
            setCustomFieldKeys([]);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (listName) fetchSubscribers(1, searchTerm);
    }, [listName]);

    useEffect(() => {
        const timeoutId = setTimeout(() => {
            if (searchTerm !== "") fetchSubscribers(1, searchTerm);
            else fetchSubscribers(1);
        }, 500);
        return () => clearTimeout(timeoutId);
    }, [searchTerm]);

    const handlePageChange = (newPage) => {
        if (newPage >= 1 && newPage <= totalPages) fetchSubscribers(newPage, searchTerm);
    };

    const handleDeleteSubscriber = async (subscriberId) => {
        if (!confirm("Delete this subscriber?")) return;
        try {
            await API.delete(`/subscribers/${subscriberId}`);
            alert("Subscriber deleted successfully");
            fetchSubscribers(currentPage, searchTerm);
        } catch {
            alert("Failed to delete subscriber");
        }
    };

    const openEditModal = (subscriber) => {
        setEditSubscriber({
            ...subscriber,
            standard_fields: { ...subscriber.standard_fields },
            custom_fields: { ...subscriber.custom_fields },
        });
        setEditModalOpen(true);
    };

    const closeEditModal = () => {
        setEditModalOpen(false);
        setEditSubscriber(null);
    };

    const handleSaveEdit = async () => {
        if (!editSubscriber) return;
        setSaving(true);
        try {
            await API.put(`/subscribers/${editSubscriber._id}`, {
                email: editSubscriber.email,
                list: listName,
                status: editSubscriber.status,
                standard_fields: editSubscriber.standard_fields,
                custom_fields: editSubscriber.custom_fields,
            });
            alert("Subscriber updated successfully");
            closeEditModal();
            fetchSubscribers(currentPage, searchTerm);
        } catch (err) {
            console.error(err);
            alert(err.response?.data?.detail || "Failed to update subscriber");
        } finally {
            setSaving(false);
        }
    };

    const renderPagination = () => {
        if (totalPages <= 1) return null;

        const getPageNumbers = () => {
            const pages = [];
            const maxVisible = 5;
            let start = Math.max(1, currentPage - Math.floor(maxVisible / 2));
            let end = Math.min(totalPages, start + maxVisible - 1);

            if (end - start + 1 < maxVisible) {
                start = Math.max(1, end - maxVisible + 1);
            }
            for (let i = start; i <= end; i++) pages.push(i);
            return pages;
        };

        return (
            <div className="flex justify-between items-center mt-6">
                <div className="text-sm text-gray-600">
                    Page {currentPage} of {totalPages} • {totalCount} total subscribers
                </div>
                <div className="flex gap-1">
                    <button
                        onClick={() => handlePageChange(1)}
                        disabled={currentPage === 1}
                        className="px-3 py-1 text-sm border rounded disabled:opacity-50 hover:bg-gray-50"
                    >
                        First
                    </button>
                    <button
                        onClick={() => handlePageChange(currentPage - 1)}
                        disabled={currentPage === 1}
                        className="px-3 py-1 text-sm border rounded disabled:opacity-50 hover:bg-gray-50"
                    >
                        Prev
                    </button>
                    {getPageNumbers().map((num) => (
                        <button
                            key={num}
                            onClick={() => handlePageChange(num)}
                            className={`px-3 py-1 text-sm border rounded ${num === currentPage ? "bg-blue-500 text-white" : "hover:bg-gray-50"
                                }`}
                        >
                            {num}
                        </button>
                    ))}
                    <button
                        onClick={() => handlePageChange(currentPage + 1)}
                        disabled={currentPage === totalPages}
                        className="px-3 py-1 text-sm border rounded disabled:opacity-50 hover:bg-gray-50"
                    >
                        Next
                    </button>
                    <button
                        onClick={() => handlePageChange(totalPages)}
                        disabled={currentPage === totalPages}
                        className="px-3 py-1 text-sm border rounded disabled:opacity-50 hover:bg-gray-50"
                    >
                        Last
                    </button>
                </div>
            </div>
        );
    };

    return (
        <div className="p-6">
            <h1 className="text-xl font-semibold mb-4">Subscribers of {listName}</h1>
            
           <button
                onClick={() => navigate('/subscribers')}
                    className="px-4 py-2 bg-blue-600 rounded hover:bg-blue-300">
                  <span>←</span>
                  <span>Back</span>
           </button>

            <input
                type="text"
                placeholder="Search by email or name..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="border px-3 py-2 rounded w-full mb-4"
            />

            {loading ? (
                <div className="flex items-center justify-center p-8">
                    <div className="animate-spin h-8 w-8 border-4 border-blue-600 border-t-transparent rounded-full"></div>
                    <span className="ml-2">Loading...</span>
                </div>
            ) : subscribers.length === 0 ? (
                <div className="text-center p-8 text-gray-500">
                    {searchTerm ? "No subscribers match your search" : "No subscribers found"}
                </div>
            ) : (
                <div className="overflow-x-auto">
                    <table className="w-full border border-gray-200">
                        <thead>
                            <tr className="bg-gray-100">
                                <th className="border p-2">Email</th>
                                <th className="border p-2">Status</th>
                                <th className="border p-2">Name</th>
                                {customFieldKeys.map((key) => (
                                    <th key={key} className="border p-2">
                                        {key}
                                    </th>
                                ))}
                                <th className="border p-2">Created</th>
                                <th className="border p-2">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {subscribers.map((sub) => (
                                <tr key={sub._id} className="border-t hover:bg-gray-50">
                                    <td className="border p-2">{sub.email}</td>
                                    <td className="border p-2">
                                        <span className={`px-2 py-1 rounded text-xs ${sub.status === 'active' ? 'bg-green-100 text-green-800' :
                                                sub.status === 'unsubscribed' ? 'bg-red-100 text-red-800' :
                                                    'bg-gray-100 text-gray-800'
                                            }`}>
                                            {sub.status}
                                        </span>
                                    </td>
                                    <td className="border p-2">
                                        {sub.standard_fields?.first_name || ''} {sub.standard_fields?.last_name || ''}
                                    </td>
                                    {customFieldKeys.map((key) => (
                                        <td key={key} className="border p-2">
                                            {sub.custom_fields?.[key] || "-"}
                                        </td>
                                    ))}
                                    <td className="border p-2 text-xs text-gray-600">
                                        {sub.created_at ? new Date(sub.created_at).toLocaleDateString() : "-"}
                                    </td>
                                    <td className="border p-2">
                                        <div className="flex gap-2">
                                            <button
                                                onClick={() => openEditModal(sub)}
                                                className="px-2 py-1 bg-blue-500 text-white rounded text-sm hover:bg-blue-600"
                                            >
                                                Edit
                                            </button>
                                            <button
                                                onClick={() => handleDeleteSubscriber(sub._id)}
                                                className="px-2 py-1 bg-red-500 text-white rounded text-sm hover:bg-red-600"
                                            >
                                                Delete
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    {renderPagination()}
                </div>
            )}

            {editModalOpen && editSubscriber && (
                <div className="fixed inset-0 flex items-center justify-center bg-black bg-opacity-40 z-50">
                    <div className="bg-white rounded shadow-lg w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto">
                        <h2 className="text-lg font-semibold mb-4">Edit Subscriber</h2>
                        <div className="space-y-3">
                            <div>
                                <label className="block text-sm font-medium mb-1">Email</label>
                                <input
                                    type="email"
                                    value={editSubscriber.email}
                                    onChange={(e) =>
                                        setEditSubscriber({ ...editSubscriber, email: e.target.value })
                                    }
                                    className="border px-3 py-2 rounded w-full"
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium mb-1">Status</label>
                                <select
                                    value={editSubscriber.status}
                                    onChange={(e) =>
                                        setEditSubscriber({ ...editSubscriber, status: e.target.value })
                                    }
                                    className="border px-3 py-2 rounded w-full"
                                >
                                    <option value="active">Active</option>
                                    <option value="unsubscribed">Unsubscribed</option>
                                    <option value="bounced">Bounced</option>
                                    <option value="inactive">Inactive</option>
                                </select>
                            </div>
                            <div>
                                <label className="block text-sm font-medium mb-1">First Name</label>
                                <input
                                    type="text"
                                    value={editSubscriber.standard_fields?.first_name || ""}
                                    onChange={(e) =>
                                        setEditSubscriber({
                                            ...editSubscriber,
                                            standard_fields: {
                                                ...editSubscriber.standard_fields,
                                                first_name: e.target.value,
                                            },
                                        })
                                    }
                                    className="border px-3 py-2 rounded w-full"
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium mb-1">Last Name</label>
                                <input
                                    type="text"
                                    value={editSubscriber.standard_fields?.last_name || ""}
                                    onChange={(e) =>
                                        setEditSubscriber({
                                            ...editSubscriber,
                                            standard_fields: {
                                                ...editSubscriber.standard_fields,
                                                last_name: e.target.value,
                                            },
                                        })
                                    }
                                    className="border px-3 py-2 rounded w-full"
                                />
                            </div>
                            {customFieldKeys.length > 0 && (
                                <div className="border-t pt-3 mt-3">
                                    <h3 className="text-sm font-medium mb-2">Custom Fields</h3>
                                    {customFieldKeys.map((key) => (
                                        <div key={key} className="mb-2">
                                            <label className="block text-sm mb-1">{key}</label>
                                            <input
                                                type="text"
                                                value={editSubscriber.custom_fields?.[key] || ""}
                                                onChange={(e) =>
                                                    setEditSubscriber({
                                                        ...editSubscriber,
                                                        custom_fields: {
                                                            ...editSubscriber.custom_fields,
                                                            [key]: e.target.value,
                                                        },
                                                    })
                                                }
                                                className="border px-3 py-2 rounded w-full"
                                            />
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>

                        <div className="mt-6 flex justify-end gap-2">
                            <button
                                onClick={closeEditModal}
                                className="px-4 py-2 border rounded hover:bg-gray-50"
                                disabled={saving}
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleSaveEdit}
                                className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50"
                                disabled={saving}
                            >
                                {saving ? "Saving..." : "Save"}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}