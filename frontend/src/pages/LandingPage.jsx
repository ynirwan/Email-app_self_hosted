import { useState } from "react";
import { Link } from "react-router-dom";
import { 
  Mail, 
  Users, 
  BarChart3, 
  Zap, 
  Layout, 
  Target, 
  Clock, 
  Shield,
  CheckCircle,
  ArrowRight,
  Send,
  TrendingUp,
  Layers,
  Settings
} from "lucide-react";

export default function LandingPage() {
  const [formData, setFormData] = useState({
    name: "",
    email: "",
    company: "",
    message: ""
  });

  const service = {
    name: "Email Marketing Platform",
    tagline: "Self-Hosted Email Marketing Made Simple",
    description: "A powerful, self-hosted email marketing platform with campaign management, subscriber lists, automation workflows, and real-time analytics. Built for businesses that value data ownership and control.",
    features: [
      "Campaign Management",
      "Drag & Drop Templates",
      "HTML Template Editor",
      "Subscriber List Management",
      "Automation Workflows",
      "A/B Testing",
      "Real-Time Analytics",
      "AWS SES Integration"
    ]
  };

  const benefits = [
    {
      icon: Mail,
      title: "Powerful Campaign Builder",
      description: "Create stunning email campaigns with our intuitive builder. Support for HTML templates and drag-and-drop editing."
    },
    {
      icon: Users,
      title: "Smart Subscriber Management",
      description: "Import, segment, and manage your subscriber lists with ease. Bulk uploads, custom fields, and automated list hygiene."
    },
    {
      icon: Zap,
      title: "Automation Workflows",
      description: "Set up triggered email sequences for welcome series, cart abandonment, re-engagement, and more."
    },
    {
      icon: BarChart3,
      title: "Real-Time Analytics",
      description: "Track opens, clicks, bounces, and conversions with detailed dashboards and exportable reports."
    }
  ];

  const automationFeatures = [
    {
      title: "Welcome Email Sequences",
      description: "Automatically greet new subscribers with personalized welcome emails and onboarding sequences.",
      examples: ["New subscriber triggers", "Multi-step sequences", "Personalized content", "Engagement tracking"]
    },
    {
      title: "Behavioral Triggers",
      description: "Send targeted emails based on subscriber actions like clicks, opens, or custom events.",
      examples: ["Cart abandonment", "Browse abandonment", "Purchase follow-ups", "Re-engagement campaigns"]
    },
    {
      title: "Dynamic Segmentation",
      description: "Create smart segments based on subscriber data, behavior, and engagement patterns.",
      examples: ["Active vs inactive", "Purchase history", "Geographic location", "Custom field filters"]
    },
    {
      title: "A/B Testing",
      description: "Optimize your campaigns with split testing for subject lines, content, and send times.",
      examples: ["Subject line tests", "Content variations", "Send time optimization", "Winner auto-selection"]
    }
  ];

  const handleSubmit = (e) => {
    e.preventDefault();
    alert("Thank you for your interest! We'll be in touch soon.");
    setFormData({ name: "", email: "", company: "", message: "" });
  };

  return (
    <div className="min-h-screen bg-white">
      {/* Hero Section */}
      <section className="bg-gradient-to-br from-blue-600 via-blue-700 to-indigo-800 text-white">
        <div className="max-w-7xl mx-auto px-4 py-20">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
            <div className="space-y-6">
              <span className="inline-block px-4 py-2 bg-blue-500 bg-opacity-30 rounded-full text-sm font-medium">
                Self-Hosted Solution
              </span>
              <h1 className="text-4xl lg:text-5xl font-bold leading-tight">
                {service.name}
              </h1>
              <p className="text-xl text-blue-100 leading-relaxed">
                {service.description}
              </p>
              <div className="bg-white bg-opacity-10 p-6 rounded-lg backdrop-blur-sm border border-white border-opacity-20">
                <h3 className="font-semibold text-white mb-2 flex items-center gap-2">
                  <Shield className="h-5 w-5" />
                  Complete Data Ownership
                </h3>
                <p className="text-blue-100">
                  Your data stays on your servers. No third-party access, no vendor lock-in, complete control over your email marketing.
                </p>
              </div>
              <div className="flex flex-col sm:flex-row gap-4">
                <Link
                  to="/login"
                  className="inline-flex items-center justify-center px-6 py-3 bg-white text-blue-700 font-semibold rounded-lg hover:bg-blue-50 transition-colors"
                >
                  Get Started
                  <ArrowRight className="ml-2 h-5 w-5" />
                </Link>
                <a
                  href="#features"
                  className="inline-flex items-center justify-center px-6 py-3 border-2 border-white text-white font-semibold rounded-lg hover:bg-white hover:text-blue-700 transition-colors"
                >
                  Explore Features
                </a>
              </div>
            </div>
            <div className="relative">
              <div className="bg-white rounded-2xl shadow-2xl p-6 transform rotate-1 hover:rotate-0 transition-transform">
                <div className="flex items-center gap-3 mb-4 pb-4 border-b">
                  <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
                    <Send className="h-5 w-5 text-blue-600" />
                  </div>
                  <div>
                    <h4 className="font-semibold text-gray-900">Campaign Dashboard</h4>
                    <p className="text-sm text-gray-500">Real-time performance</p>
                  </div>
                </div>
                <div className="space-y-4">
                  <div className="flex justify-between items-center">
                    <span className="text-gray-600">Emails Sent</span>
                    <span className="font-bold text-gray-900">125,847</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-gray-600">Open Rate</span>
                    <span className="font-bold text-green-600">24.8%</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-gray-600">Click Rate</span>
                    <span className="font-bold text-blue-600">4.2%</span>
                  </div>
                  <div className="w-full bg-gray-100 rounded-full h-2">
                    <div className="bg-blue-600 h-2 rounded-full" style={{ width: "72%" }}></div>
                  </div>
                  <p className="text-xs text-gray-500 text-center">Campaign Progress: 72% delivered</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Benefits Section */}
      <section id="features" className="py-20 bg-gray-50">
        <div className="max-w-7xl mx-auto px-4">
          <div className="text-center mb-12">
            <h2 className="text-3xl lg:text-4xl font-bold text-gray-900 mb-4">
              Everything You Need for Email Marketing
            </h2>
            <p className="text-xl text-gray-600 max-w-3xl mx-auto">
              A complete email marketing toolkit with powerful features designed to help you grow your audience and drive results.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {benefits.map((benefit, index) => (
              <div key={index} className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 text-center hover:shadow-lg transition-shadow">
                <div className="w-14 h-14 bg-blue-100 rounded-xl flex items-center justify-center mx-auto mb-4">
                  <benefit.icon className="h-7 w-7 text-blue-600" />
                </div>
                <h3 className="text-lg font-semibold text-gray-900 mb-2">{benefit.title}</h3>
                <p className="text-gray-600 text-sm">{benefit.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Automation Features */}
      <section className="py-20">
        <div className="max-w-7xl mx-auto px-4">
          <div className="text-center mb-12">
            <h2 className="text-3xl lg:text-4xl font-bold text-gray-900 mb-4">
              Powerful Automation Capabilities
            </h2>
            <p className="text-xl text-gray-600 max-w-3xl mx-auto">
              Set up intelligent email workflows that work around the clock to engage your subscribers.
            </p>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            {automationFeatures.map((feature, index) => (
              <div key={index} className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 hover:shadow-lg transition-shadow">
                <h3 className="text-xl font-semibold text-gray-900 mb-3">{feature.title}</h3>
                <p className="text-gray-600 mb-4">{feature.description}</p>
                <div className="grid grid-cols-2 gap-2">
                  {feature.examples.map((example, idx) => (
                    <div key={idx} className="flex items-center text-sm text-gray-600">
                      <CheckCircle className="h-4 w-4 text-green-500 mr-2 flex-shrink-0" />
                      {example}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section className="py-20 bg-gray-50">
        <div className="max-w-7xl mx-auto px-4">
          <div className="text-center mb-12">
            <h2 className="text-3xl lg:text-4xl font-bold text-gray-900 mb-4">
              Simple 4-Step Setup
            </h2>
            <p className="text-xl text-gray-600 max-w-3xl mx-auto">
              Get your email marketing platform up and running in minutes.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
            {[
              {
                step: "1",
                icon: Settings,
                title: "Configure Email Provider",
                description: "Connect AWS SES or your custom SMTP server for reliable email delivery."
              },
              {
                step: "2",
                icon: Users,
                title: "Import Subscribers",
                description: "Upload your subscriber lists via CSV with automatic field mapping."
              },
              {
                step: "3",
                icon: Layout,
                title: "Create Templates",
                description: "Design beautiful emails with our drag-and-drop builder or HTML editor."
              },
              {
                step: "4",
                icon: Send,
                title: "Launch Campaigns",
                description: "Send one-time campaigns or set up automated sequences that run 24/7."
              }
            ].map((item, index) => (
              <div key={index} className="text-center">
                <div className="w-16 h-16 bg-blue-600 rounded-full flex items-center justify-center mx-auto mb-4 relative">
                  <item.icon className="h-7 w-7 text-white" />
                  <span className="absolute -top-2 -right-2 w-7 h-7 bg-indigo-500 rounded-full flex items-center justify-center text-white font-bold text-sm">
                    {item.step}
                  </span>
                </div>
                <h3 className="text-lg font-semibold text-gray-900 mb-2">{item.title}</h3>
                <p className="text-gray-600 text-sm">{item.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Feature List */}
      <section className="py-20">
        <div className="max-w-5xl mx-auto px-4">
          <div className="text-center mb-12">
            <h2 className="text-3xl lg:text-4xl font-bold text-gray-900 mb-4">
              Complete Feature Set
            </h2>
            <p className="text-xl text-gray-600">
              Everything you need for professional email marketing campaigns.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {service.features.map((feature, index) => (
              <div key={index} className="flex items-center space-x-3 p-3 bg-gray-50 rounded-lg">
                <CheckCircle className="h-5 w-5 text-green-500 flex-shrink-0" />
                <span className="text-gray-700 font-medium">{feature}</span>
              </div>
            ))}
          </div>

          <div className="mt-12 grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="bg-blue-50 rounded-xl p-6 text-center">
              <TrendingUp className="h-10 w-10 text-blue-600 mx-auto mb-3" />
              <h4 className="font-semibold text-gray-900 mb-2">High Deliverability</h4>
              <p className="text-sm text-gray-600">Built-in suppression management, bounce handling, and compliance features.</p>
            </div>
            <div className="bg-green-50 rounded-xl p-6 text-center">
              <Layers className="h-10 w-10 text-green-600 mx-auto mb-3" />
              <h4 className="font-semibold text-gray-900 mb-2">Scalable Architecture</h4>
              <p className="text-sm text-gray-600">Handle millions of subscribers with Celery background processing.</p>
            </div>
            <div className="bg-purple-50 rounded-xl p-6 text-center">
              <Target className="h-10 w-10 text-purple-600 mx-auto mb-3" />
              <h4 className="font-semibold text-gray-900 mb-2">Smart Segmentation</h4>
              <p className="text-sm text-gray-600">8+ filter types for precise audience targeting and personalization.</p>
            </div>
          </div>
        </div>
      </section>

      {/* Stats Section */}
      <section className="py-16 bg-blue-600 text-white">
        <div className="max-w-7xl mx-auto px-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8 text-center">
            <div>
              <div className="text-4xl font-bold mb-2">100K+</div>
              <div className="text-blue-200">Emails Per Hour</div>
            </div>
            <div>
              <div className="text-4xl font-bold mb-2">99.9%</div>
              <div className="text-blue-200">Uptime SLA</div>
            </div>
            <div>
              <div className="text-4xl font-bold mb-2">8+</div>
              <div className="text-blue-200">Segment Filters</div>
            </div>
            <div>
              <div className="text-4xl font-bold mb-2">24/7</div>
              <div className="text-blue-200">Automation Running</div>
            </div>
          </div>
        </div>
      </section>

      {/* Contact Form */}
      <section id="contact" className="py-20 bg-gray-900 text-white">
        <div className="max-w-4xl mx-auto px-4">
          <div className="text-center mb-12">
            <h2 className="text-3xl lg:text-4xl font-bold mb-4">
              Ready to Get Started?
            </h2>
            <p className="text-xl text-gray-400">
              Contact us to learn more about deploying your own email marketing platform.
            </p>
          </div>

          <div className="bg-gray-800 rounded-2xl p-8">
            <form onSubmit={handleSubmit} className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">Name</label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    className="w-full px-4 py-3 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder="Your name"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">Email</label>
                  <input
                    type="email"
                    value={formData.email}
                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                    className="w-full px-4 py-3 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder="you@company.com"
                    required
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Company</label>
                <input
                  type="text"
                  value={formData.company}
                  onChange={(e) => setFormData({ ...formData, company: e.target.value })}
                  className="w-full px-4 py-3 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="Your company"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Message</label>
                <textarea
                  value={formData.message}
                  onChange={(e) => setFormData({ ...formData, message: e.target.value })}
                  rows={4}
                  className="w-full px-4 py-3 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="Tell us about your email marketing needs..."
                  required
                />
              </div>
              <button
                type="submit"
                className="w-full py-3 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 transition-colors flex items-center justify-center gap-2"
              >
                <Send className="h-5 w-5" />
                Send Message
              </button>
            </form>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-8 bg-gray-950 text-gray-400">
        <div className="max-w-7xl mx-auto px-4 text-center">
          <div className="flex items-center justify-center gap-2 mb-4">
            <Mail className="h-6 w-6 text-blue-500" />
            <span className="font-semibold text-white">Email Marketing Platform</span>
          </div>
          <p className="text-sm">
            Self-hosted email marketing solution. Your data, your control.
          </p>
        </div>
      </footer>
    </div>
  );
}
