import type { CommunityComment } from "../../lib/communityApi";

function sortByLikes(a: CommunityComment, b: CommunityComment) {
  const likes = (b.like_count ?? 0) - (a.like_count ?? 0);
  return likes || (a.created_at || "").localeCompare(b.created_at || "");
}

/** Flatten legacy nested replies for the two-level UI, without changing stored relationships. */
export function groupCommentThreads(comments: CommunityComment[]) {
  const byId = new Map(comments.map((comment) => [comment.id, comment]));
  const rootIds = new Map<number, number>();

  for (const comment of comments) {
    const path: number[] = [];
    const visited = new Set<number>();
    let current = comment;
    while (!rootIds.has(current.id) && !visited.has(current.id)) {
      path.push(current.id);
      visited.add(current.id);
      const parent = current.parent_id ? byId.get(current.parent_id) : undefined;
      if (!parent || parent.post_id !== comment.post_id) break;
      current = parent;
    }
    // Missing parents remain visible. Cycles use a stable representative and cannot loop forever.
    const cycleStart = path.indexOf(current.id);
    const rootId = rootIds.get(current.id) ?? (
      current.parent_id && visited.has(current.parent_id)
        ? Math.min(...path.slice(cycleStart))
        : current.id
    );
    for (const id of path) rootIds.set(id, rootId);
  }

  const roots: CommunityComment[] = [];
  const repliesByRoot = new Map<number, CommunityComment[]>();
  for (const comment of comments) {
    const rootId = rootIds.get(comment.id)!;
    const parent = comment.parent_id ? byId.get(comment.parent_id) : undefined;
    const displayComment = !comment.reply_to && parent && parent.post_id === comment.post_id
      ? { ...comment, reply_to: parent.author }
      : comment;
    if (rootId === comment.id) {
      roots.push(displayComment);
    } else {
      const replies = repliesByRoot.get(rootId) || [];
      replies.push(displayComment);
      repliesByRoot.set(rootId, replies);
    }
  }
  roots.sort(sortByLikes);
  for (const replies of repliesByRoot.values()) replies.sort(sortByLikes);
  return { roots, repliesByRoot };
}
