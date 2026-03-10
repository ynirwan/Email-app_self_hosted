import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import API from '../api';
import { Plus, Edit2, Trash2, Eye } from 'lucide-react';

export default function Forms() {
  const navigate = useNavigate();
  const [forms, setForms] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newForm, setNewForm] = useState({
    name: '',
    description: '',
    opt_in_type: 'single', // single, double
    fields: [],
    enabled: true,
  });

  useEffect(() => {
    fetchForms();
  }, []);

  const fetchForms = async () => {
    try {
      setLoading(true);
      const response = await API.get('/forms');
      setForms(response.data.forms || []);
    } catch (error) {
      console.error('Error fetching forms:', error);
    } finally {
      setLoading(false);
    }
  };

  const createForm = async () => {
    if (!newForm.name.trim()) {
      alert('Form name is required');
      return;
    }

    try {
      const response = await API.post('/forms', newForm);
      setForms([...forms, response.data.form]);
      setShowCreateModal(false);
      setNewForm({
        name: '',
        description: '',
        opt_in_type: 'single',
        fields: [],
        enabled: true,
      });
      alert('Form created successfully!');
    } catch (error) {
      console.error('Error creating form:', error);
      alert('Failed to create form');
    }
  };

  const deleteForm = async (formId) => {
    if (!confirm('Are you sure you want to delete this form?')) return;

    try {
      await API.delete(`/forms/${formId}`);
      setForms(forms.filter((f) => f._id !== formId));
      alert('Form deleted successfully!');
    } catch (error) {
      console.error('Error deleting form:', error);
      alert('Failed to delete form');
    }
  };

  const toggleFormStatus = async (formId, currentStatus) => {
    try {
      const response = await API.patch(`/forms/${formId}`, {
        enabled: !currentStatus,
      });
      setForms(forms.map((f) => (f._id === formId ? response.data.form : f)));
    } catch (error) {
      console.error('Error updating form:', error);
    }
  };

  if (loading) {
    return (
      <div className="animate-pulse space-y-6">
        <div className="h-8 bg-gray-200 rounded w-1/4"></div>
        <div className="space-y-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-20 bg-gray-200 rounded"></div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col lg:flex-row lg:justify-between lg:items-center space-y-4 lg:space-y-0">
        <h1 className="text-2xl font-bold text-gray-900">📋 Subscription Forms</h1>
        <button
          onClick={() => setShowCreateModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
          data-testid="button-create-form"
        >
          <Plus size={18} />
          Create Form
        </button>
      </div>

      {/* Create Form Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl p-8 max-w-md w-full">
            <h2 className="text-xl font-bold text-gray-900 mb-4">Create New Form</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Form Name
                </label>
                <input
                  type="text"
                  value={newForm.name}
                  onChange={(e) => setNewForm({ ...newForm, name: e.target.value })}
                  className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                  placeholder="e.g., Newsletter Signup"
                  data-testid="input-form-name"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Description
                </label>
                <textarea
                  value={newForm.description}
                  onChange={(e) => setNewForm({ ...newForm, description: e.target.value })}
                  className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 h-24"
                  placeholder="Describe this form..."
                  data-testid="input-form-description"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Opt-In Type
                </label>
                <select
                  value={newForm.opt_in_type}
                  onChange={(e) => setNewForm({ ...newForm, opt_in_type: e.target.value })}
                  className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                  data-testid="select-opt-in-type"
                >
                  <option value="single">
                    ✅ Single Opt-In (Immediate Subscription)
                  </option>
                  <option value="double">
                    📧 Double Opt-In (Email Confirmation Required)
                  </option>
                </select>
                <p className="mt-2 text-xs text-gray-500">
                  {newForm.opt_in_type === 'single'
                    ? 'Users are added immediately when they submit the form.'
                    : 'Users receive a confirmation email and must click the link to confirm.'}
                </p>
              </div>

              <div className="flex gap-3 pt-4">
                <button
                  onClick={() => setShowCreateModal(false)}
                  className="flex-1 px-4 py-2 border rounded-lg hover:bg-gray-50 transition"
                  data-testid="button-cancel"
                >
                  Cancel
                </button>
                <button
                  onClick={createForm}
                  className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
                  data-testid="button-create"
                >
                  Create
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Forms List */}
      <div className="space-y-4">
        {forms.length === 0 ? (
          <div className="bg-white p-12 rounded-lg shadow border text-center">
            <p className="text-gray-500 mb-4">No forms created yet.</p>
            <button
              onClick={() => setShowCreateModal(true)}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
              data-testid="button-create-first"
            >
              Create Your First Form
            </button>
          </div>
        ) : (
          <div className="grid gap-4">
            {forms.map((form) => (
              <div
                key={form._id}
                className="bg-white p-6 rounded-lg shadow border hover:shadow-lg transition"
                data-testid={`card-form-${form._id}`}
              >
                <div className="flex flex-col md:flex-row md:justify-between md:items-start gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      <h3 className="text-lg font-semibold text-gray-900">{form.name}</h3>
                      <span
                        className={`px-3 py-1 rounded-full text-xs font-medium ${
                          form.enabled
                            ? 'bg-green-100 text-green-700'
                            : 'bg-gray-100 text-gray-700'
                        }`}
                        data-testid={`status-${form._id}`}
                      >
                        {form.enabled ? 'Active' : 'Inactive'}
                      </span>
                    </div>
                    <p className="text-sm text-gray-600 mb-2">{form.description}</p>
                    <div className="flex items-center gap-2 text-sm text-gray-500">
                      <span className="inline-block px-3 py-1 bg-blue-100 text-blue-700 rounded-full text-xs font-medium">
                        {form.opt_in_type === 'single'
                          ? '✅ Single Opt-In'
                          : '📧 Double Opt-In'}
                      </span>
                      {form.subscriber_count && (
                        <span className="text-gray-600">
                          {form.subscriber_count} subscribers
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="flex flex-col gap-2">
                    <button
                      onClick={() => navigate(`/forms/${form._id}/edit`)}
                      className="flex items-center gap-2 px-4 py-2 bg-blue-100 text-blue-700 rounded-lg hover:bg-blue-200 transition"
                      data-testid={`button-edit-${form._id}`}
                    >
                      <Edit2 size={16} />
                      Design
                    </button>
                    <button
                      onClick={() => navigate(`/forms/${form._id}/preview`)}
                      className="flex items-center gap-2 px-4 py-2 bg-purple-100 text-purple-700 rounded-lg hover:bg-purple-200 transition"
                      data-testid={`button-preview-${form._id}`}
                    >
                      <Eye size={16} />
                      Preview
                    </button>
                    <button
                      onClick={() => toggleFormStatus(form._id, form.enabled)}
                      className={`px-4 py-2 rounded-lg transition ${
                        form.enabled
                          ? 'bg-yellow-100 text-yellow-700 hover:bg-yellow-200'
                          : 'bg-green-100 text-green-700 hover:bg-green-200'
                      }`}
                      data-testid={`button-toggle-${form._id}`}
                    >
                      {form.enabled ? 'Disable' : 'Enable'}
                    </button>
                    <button
                      onClick={() => deleteForm(form._id)}
                      className="flex items-center gap-2 px-4 py-2 bg-red-100 text-red-700 rounded-lg hover:bg-red-200 transition"
                      data-testid={`button-delete-${form._id}`}
                    >
                      <Trash2 size={16} />
                      Delete
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
