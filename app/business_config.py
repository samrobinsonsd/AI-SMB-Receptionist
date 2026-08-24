# Central business configuration for the AI receptionist.
#
# Business-specific information lives here instead of being hardcoded
# throughout the voice application.
#
# Later, this configuration could be loaded from a database, admin
# portal, CRM, or other external business system.

BUSINESS_CONFIG = {
    # Basic business identity.
    "name": "Reefwise",

    "description": (
        "Reefwise is an aquarium store specializing in coral, "
        "saltwater aquariums, and marine life."
    ),

    # Opening greeting used when the receptionist answers the call.
    "greeting": (
        "Thank you for calling Reefwise, your aquatic solution provider. "
        "How can I help you today?"
    ),

    # Public contact information.
    "address": "5401 Patton Drive, Suite 105, Lisle, Illinois 60532",
    "phone": "(630) 541-5486",

    # Published store hours.
    "hours": {
        "monday": "2:00 PM to 8:00 PM",
        "tuesday": "2:00 PM to 8:00 PM",
        "wednesday": "4:00 PM to 8:00 PM",
        "thursday": "2:00 PM to 8:00 PM",
        "friday": "4:00 PM to 8:00 PM",
        "saturday": "11:00 AM to 5:00 PM",
        "sunday": "11:00 AM to 5:00 PM",
    },

    # General information the receptionist may safely discuss.
    "specialties": [
        "Coral",
        "Saltwater aquariums",
        "Marine life",
        "Aquascaping",
    ],
    
# Confirmed services, products, and business capabilities.
#
# These are static facts the receptionist may answer directly.
"knowledge": {
    "services": [
        "RO/DI water",
        "Prepared saltwater",
        "Aquarium maintenance",
        "ICP testing",
        "House calls",
        "Aquarium tear-downs",
        "Aquascaping",
        "Aquarium builds",
        "Custom aquarium work",
    ],

    "livestock": [
        "Saltwater fish",
        "Coral Frags",
        "Coral Colonies",
        "Invertebrates",
        "Cleanup Crew",
    ],

    "livestock_practices": [
        "All fish are quarantined prior to sale",
    ],

    "products": [
        "Aquarium salts",
        "Water additives",
        "Frozen fish food",
        "Dry fish food",
        "Aquarium lights",
        "Pumps",
        "Protein skimmers",
        "Automatic feeders and top-offs",
        "New aquariums",
        "Used aquariums",
        "Aquarium equipment",
    ],
},

    # Information that must not be guessed.
    #
    # These items will eventually be handled by tools or escalation
    # rather than relying on the language model's general knowledge.
    "restricted_information": [
        "Current livestock inventory",
        "Current coral inventory",
        "Current product inventory",
        "Current pricing",
        "Exact product availability",
        "Special-order availability",
    ],
}