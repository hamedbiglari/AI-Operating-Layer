<?php
/**
 * Maps a WordPress post to a Cloud Core object.
 *
 * The Core object id is stored in post meta because WordPress needs to know
 * *which* Core object a post represents. That is the ONLY Core-derived value
 * this plugin persists locally, and it is an identifier, not truth: nothing
 * about the product's name, price, evidence or trust is copied here.
 *
 * A merchant types the Core object id once (or picks it); the plugin never
 * guesses it from a title or slug, because two products can share a name and
 * a wrong mapping would attach one product's evidence to another.
 */

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit;
}

class AIOL_Mappings
{
    public const META_OBJECT_ID   = '_aiol_object_id';
    public const META_OBJECT_TYPE = '_aiol_object_type';
    public const META_SYNC_STATE  = '_aiol_sync_state';
    public const META_SYNC_ERROR  = '_aiol_sync_error';

    public static function object_id(int $post_id): string
    {
        return (string) get_post_meta($post_id, self::META_OBJECT_ID, true);
    }

    public static function object_type(int $post_id): string
    {
        $type = (string) get_post_meta($post_id, self::META_OBJECT_TYPE, true);
        return $type !== '' ? $type : 'knowledge_object';
    }

    public static function is_mapped(int $post_id): bool
    {
        return self::object_id($post_id) !== '';
    }

    public static function set_state(int $post_id, string $state, string $error = ''): void
    {
        update_post_meta($post_id, self::META_SYNC_STATE, $state);
        if ($error === '') {
            delete_post_meta($post_id, self::META_SYNC_ERROR);
        } else {
            update_post_meta($post_id, self::META_SYNC_ERROR, $error);
        }
    }

    public static function state(int $post_id): string
    {
        $state = (string) get_post_meta($post_id, self::META_SYNC_STATE, true);
        return $state !== '' ? $state : 'not_configured';
    }

    public static function error(int $post_id): string
    {
        return (string) get_post_meta($post_id, self::META_SYNC_ERROR, true);
    }

    /** UUID shape check before a round trip. Core is still the authority. */
    public static function looks_like_uuid(string $value): bool
    {
        return (bool) preg_match(
            '/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i',
            $value
        );
    }

    public static function allowed_object_types(): array
    {
        return ['knowledge_object', 'product'];
    }
}
