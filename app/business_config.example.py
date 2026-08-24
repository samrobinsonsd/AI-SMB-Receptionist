# Central business configuration for the AI receptionist.
#
# Copy this file to:
#
#     app/business_config.py
#
# Then replace the example values below with information about
# your business.
#
# business_config.py should NOT be committed to source control.
#
# Later, this configuration could be loaded from a database, admin
# portal, CRM, or other external business system.

BUSINESS_CONFIG = {
    # Basic business identity.
    "name": "Example Business",

    "description": (
        "Example Business is a local specialty retailer providing "
        "products, services, and support to its customers."
    ),

    # Opening greeting used when the receptionist answers the call.
    "greeting": (
        "Thank you for calling Example Business. "
        "How can I help you today?"
    ),

    # Public contact information.
    "address": "123 Main Street, Suite 100, Example City, Illinois 60000",
    "phone": "(555) 555-0100",

    # Published business hours.
    "hours": {
        "monday": "9:00 AM to 5:00 PM",
        "tuesday": "9:00 AM to 5:00 PM",
        "wednesday": "9:00 AM to 5:00 PM",
        "thursday": "9:00 AM to 5:00 PM",
        "friday": "9:00 AM to 5:00 PM",
        "saturday": "10:00 AM to 4:00 PM",
        "sunday": "Closed",
    },

    # General information the receptionist may safely discuss.
    "specialties": [
        "Specialty products",
        "Customer consultation",
        "Professional services",
        "Custom solutions",
    ],

    # Confirmed services, products, and business capabilities.
    #
    # These are static facts the receptionist may answer directly.
    "knowledge": {
        "services": [
            "Consultations",
            "Installation",
            "Maintenance",
            "Testing",
            "On-site service",
            "Custom projects",
        ],

        "livestock": [
            # This category can be renamed or repurposed if it does
            # not apply to your business.
            "Example livestock category",
            "Example livestock category",
        ],

        "livestock_practices": [
            # Example:
            # "All livestock is inspected prior to sale",
        ],

        "products": [
            "Example product category",
            "Example equipment category",
            "Replacement parts",
            "Accessories",
            "New equipment",
            "Used equipment",
        ],
    },

    # Information that must not be guessed.
    #
    # Add any information here that changes frequently or should
    # require a tool lookup, database query, or human escalation.
    "restricted_information": [
        "Current inventory",
        "Current pricing",
        "Exact product availability",
        "Special-order availability",
    ],
}