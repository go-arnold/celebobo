# 11. Error codes

Every error is a `problem+json` body: `{ type, title, status, code, detail, errors?, meta?, request_id }`.
`code` is stable and meant for the frontend; `detail` is a French message ready to display;
`errors` holds per-field messages for validation errors; `meta` carries extra data (e.g. `available` for stock,
`from`/`to` for a refused transition). Quote `request_id` when reporting a problem.

## Generic codes

| HTTP | Code | When |
|---|---|---|
| 400 | `validation_failed` | Invalid input (see `errors`), including a missing `Idempotency-Key` |
| 401 | `not_authenticated` | Not logged in or session expired |
| 403 | `forbidden` / `permission_denied` | Logged in but not allowed |
| 404 | `not_found` | Unknown resource, or outside the user's scope |
| 409 | `conflict` | State conflict |
| 422 | `invalid_transition` | Order status change not allowed for this user (`meta.from`, `meta.to`) |
| 422 | `insufficient_stock` | Not enough stock (`meta.available`) |
| 429 | `rate_limited` / `throttled` | Too many requests |
| 503 | `service_unavailable` | Temporary outage |

## Accounts

| HTTP | Code | Message |
|---|---|---|
| 400 | `email_already_used` | Un compte existe déjà avec cette adresse e-mail. |
| 400 | `phone_already_used` | Ce numéro de téléphone est déjà utilisé. |
| 400 | `unknown_referral_code` | Aucun revendeur trouvé avec ce code. |
| 400 | `weak_password` | Le mot de passe ne respecte pas les règles de sécurité. |
| 422 | `referral_already_set` | Un code revendeur est déjà associé à votre compte. |
| 422 | `self_referral` | Vous ne pouvez pas utiliser votre propre code revendeur. |
| 503 | `referral_codes_exhausted` | Impossible de générer un code revendeur pour le moment. |
| 422 | `address_book_full` | Vous avez atteint le nombre maximal d'adresses. |
| 404 | `address_not_found` | Adresse introuvable. |
| 404 | `user_not_found` | Utilisateur introuvable. |
| 422 | `staff_account_deletion` | Les comptes revendeur et administrateur doivent être désactivés par un administrateur. |
| 403 | `own_role_change` | Vous ne pouvez pas modifier votre propre rôle. |
| 400 | `invalid_role` | Rôle invalide. |
| 422 | `not_a_reseller` | Seuls les revendeurs ont une disponibilité. |
| 404 | `reseller_not_found` | Revendeur introuvable. |
| 409 | `already_reseller` | Cette personne est déjà revendeur. |
| 422 | `staff_cannot_become_reseller` | Un compte responsable ou administrateur ne peut pas devenir revendeur. |
| 400 | `invalid_manager` | Le responsable doit être un membre actif de l'équipe. |
| 403 | `own_account_deactivation` | Vous ne pouvez pas désactiver votre propre compte. |
| 422 | `inactive_account` | Ce compte est désactivé. |
| 429 | `too_many_login_attempts` | Trop de tentatives de connexion. Réessayez dans quelques minutes. |
| 400 | `invalid_avatar` | Cette photo est introuvable ou ne vous appartient pas. |

## Assistant

| HTTP | Code | Message |
|---|---|---|
| 404 | `assistant_session_not_found` | Conversation introuvable. |
| 400 | `question_too_long` | La question est trop longue. |
| 503 | `assistant_quota_exceeded` | L'assistant a atteint sa limite du jour. Réessayez demain. |
| 503 | `assistant_unavailable` | L'assistant est momentanément indisponible. |

## Audit

| HTTP | Code | Message |
|---|---|---|
| 404 | `audit_entry_not_found` | Entrée du journal introuvable. |

## Catalogue

| HTTP | Code | Message |
|---|---|---|
| 404 | `product_not_found` | Produit introuvable. |
| 404 | `category_not_found` | Catégorie introuvable. |
| 422 | `review_not_allowed` | Seuls les clients ayant reçu ce produit peuvent laisser un avis. |
| 422 | `product_unavailable` | Ce produit n'est plus disponible. |
| 422 | `variant_required` | Choisissez une variante pour ce produit. |
| 422 | `insufficient_stock` |  |
| 400 | `invalid_pricing` | Les prix du produit sont incohérents. |
| 400 | `sell_by_in_past` | La date limite de vente ne peut pas être passée. |
| 400 | `category_name_taken` | Une catégorie porte déjà ce nom. |
| 409 | `category_not_empty` | Cette catégorie contient encore des produits. Choisissez où les déplacer. |
| 400 | `invalid_variant_attributes` | Les attributs de la variante sont invalides. |
| 400 | `duplicate_sku` | Ce SKU est déjà utilisé. |
| 400 | `duplicate_variant` | Une variante avec ces attributs existe déjà. |
| 404 | `variant_not_found` | Variante introuvable. |
| 422 | `variants_manage_stock` | Le stock de ce produit se gère par variante. |
| 422 | `negative_stock` | Le stock ne peut pas devenir négatif. |
| 400 | `unknown_images` | Certaines images sont introuvables. Téléversez-les d'abord. |
| 404 | `review_not_found` | Avis introuvable. |

## Site content

| HTTP | Code | Message |
|---|---|---|
| 404 | `contact_message_not_found` | Message introuvable. |
| 404 | `page_not_found` | Page introuvable. |
| 404 | `faq_entry_not_found` | Question introuvable. |
| 404 | `banner_not_found` | Bannière introuvable. |
| 409 | `slug_taken` | Une page utilise déjà cette adresse. |
| 404 | `unknown_subscription` | Lien de désinscription invalide. |
| 400 | `invalid_schedule` | La fin doit suivre le début. |
| 400 | `unknown_payment_method` | Moyen de paiement inconnu. |

## Documents and jobs

| HTTP | Code | Message |
|---|---|---|
| 404 | `job_not_found` | Tâche introuvable. |
| 409 | `job_not_ready` | Le fichier n'est pas encore disponible. |
| 400 | `unsupported_format` | Format non pris en charge pour ce document. |
| 400 | `invalid_import_file` | Fichier d'import invalide. |
| 409 | `invoice_unavailable` | La facture n'est pas disponible pour une commande annulée. |

## Uploads

| HTTP | Code | Message |
|---|---|---|
| 403 | `upload_not_allowed` | Vous ne pouvez pas téléverser ce type de fichier. |
| 400 | `invalid_upload` | Le fichier téléversé n'a pas pu être vérifié. |
| 400 | `upload_too_large` | Le fichier est trop volumineux. |
| 400 | `unsupported_format` | Format de fichier non pris en charge. |
| 404 | `media_not_found` | Fichier introuvable. |
| 503 | `storage_not_configured` | Le stockage des fichiers n'est pas configuré. |
| 503 | `media_storage_unavailable` | Le stockage des fichiers est momentanément indisponible. |

## Messaging

| HTTP | Code | Message |
|---|---|---|
| 404 | `conversation_not_found` | Discussion introuvable. |
| 422 | `conversation_closed` | Cette discussion est clôturée. |
| 400 | `empty_message` | Le message est vide. |
| 422 | `not_an_order_conversation` | Les propositions de prix se font dans la discussion d'une commande. |
| 422 | `not_a_support_conversation` | Seules les discussions d'assistance peuvent être assignées. |
| 404 | `proposal_not_found` | Proposition introuvable. |
| 409 | `proposal_already_answered` | Cette proposition a déjà reçu une réponse. |
| 404 | `notification_not_found` | Notification introuvable. |

## Cart, checkout and orders

| HTTP | Code | Message |
|---|---|---|
| 404 | `order_not_found` | Commande introuvable. |
| 400 | `empty_order` | Votre commande ne contient aucun article. |
| 400 | `too_many_lines` | Votre commande contient trop d'articles différents. |
| 400 | `address_required` | Indiquez une adresse de livraison. |
| 400 | `reseller_not_found` | Revendeur introuvable ou inactif. |
| 422 | `assignment_closed` | Cette commande ne peut plus être réassignée. |
| 403 | `not_assigned_to_you` | Cette commande ne vous est pas assignée. |
| 404 | `cart_line_not_found` | Article introuvable dans le panier. |
| 422 | `item_not_adjustable` | Le prix ne peut plus être modifié pour cette commande. |
| 400 | `invalid_proposed_price` | Le prix proposé doit être positif et ne pas dépasser le prix catalogue. |
| 404 | `order_item_not_found` | Article introuvable dans cette commande. |
| 400 | `coupon_rejected` | Ce code promo n'est pas valable. |
| 404 | `shipping_zone_not_found` | Zone de livraison introuvable. |
| 404 | `coupon_not_found` | Code promo introuvable. |
| 409 | `coupon_code_taken` | Un code promo utilise déjà ce code. |

## Push notifications

| HTTP | Code | Message |
|---|---|---|
| 404 | `device_not_found` | Appareil introuvable. |
| 422 | `too_many_devices` | Trop d'appareils enregistrés pour ce compte. |

## Resellers

| HTTP | Code | Message |
|---|---|---|
| 404 | `application_not_found` | Candidature introuvable. |
| 409 | `application_pending` | Une candidature est déjà en cours d'examen pour cette adresse e-mail. |
| 409 | `already_reseller` | Cette adresse e-mail appartient déjà à un revendeur. |
| 409 | `application_reviewed` | Cette candidature a déjà été traitée. |
| 404 | `no_referral_code` | Aucun code revendeur n'est associé à votre compte. |

## Sales and commissions

| HTTP | Code | Message |
|---|---|---|
| 404 | `sale_not_found` | Vente introuvable. |
| 422 | `sale_not_editable` | Seules les ventes valides peuvent être modifiées. |
| 400 | `invalid_sale_date` | La date de vente ne peut pas être dans le futur. |
| 400 | `seller_required` | Indiquez le revendeur à qui attribuer la vente. |
| 400 | `invalid_seller` | Ce vendeur est introuvable ou inactif. |
| 400 | `refund_exceeds_total` | Le montant dépasse ce qui reste remboursable. |
| 422 | `already_returned` | Cette vente a déjà été retournée. |
| 409 | `order_not_convertible` | Cette commande ne peut pas être convertie en ventes. |
| 400 | `unknown_order_items` | Certains articles n'appartiennent pas à cette commande. |
| 400 | `payout_exceeds_due` | Le montant dépasse la commission due. |
| 400 | `not_a_reseller` | Cet utilisateur n'est pas revendeur. |
| 422 | `return_through_order` | Cette vente provient d'une commande : enregistrez le retour sur la commande. |

## Coupon refusal reasons

`coupon_rejected` carries a reason in `meta`: `unknown`, `inactive`, `not_started`, `expired`,
`minimum` (with the minimum subtotal), `login_required`, `exhausted`, `already_used` — see §4.

## Conversion refusal reasons

`order_not_convertible` carries: `cancelled`, `returned`, `already_converted`, `no_products` — see §5.
