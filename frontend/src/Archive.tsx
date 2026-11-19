import { usePolling, topicsPath } from './api';
import type { Topic, TopicDetail } from './api';
import { Link } from './navigation';
import { Meta } from './ui';

export function Archive({ slug, id }: { slug?: string; id?: string }) {
  const path = slug ? '/api/communities/' + slug + '/topics' : topicsPath;
  return <>
    <Link className="back" href={id ? slug ? '/places/' + slug : '/archive' : '/'}>{id ? '返回旧版讨论' : '返回附近需求'}</Link>
    {id ? <ArchivedTopic path={path + '/' + id} /> : <ArchivedFeed path={path} slug={slug} />}
  </>;
}

function ArchivedFeed({ path, slug }: { path: string; slug?: string }) {
  const { data, error } = usePolling<Topic[]>(path, 12000);
  return <section className="card detail">
    <h1>旧版讨论</h1>
    {error && <p role="status">{error.message}</p>}
    {data?.length === 0 && <p className="quiet">暂无旧版讨论。</p>}
    <ul className="hot-list">{data?.map((topic) => <li key={topic.id}>
      <Link className="hot-link" href={(slug ? '/places/' + slug : '') + '/topics/' + topic.id}>{topic.title}</Link>
      <span className="hot-meta">{topic.nickname} · {topic.comment_count} 条评论</span>
    </li>)}</ul>
  </section>;
}

function ArchivedTopic({ path }: { path: string }) {
  const { data, error } = usePolling<TopicDetail>(path, 12000);
  if (!data) return <p className="notice" role="status">{error?.message ?? '正在加载旧版话题…'}</p>;
  return <>
    <article className="card detail">
      <Meta post={data} />
      <h1>{data.title}</h1>
      <p className="post-content">{data.content}</p>
      {data.hot_topic && <a className="back" href={data.hot_topic.original_url} target="_blank"
        rel="noopener noreferrer">查看原文</a>}
    </article>
    <section className="card discussion">
      <h2>历史评论</h2>
      <ul className="comments">{data.comments.map((comment) => <li key={comment.id}>
        <Meta post={comment} /><p className="post-content">{comment.content}</p>
      </li>)}</ul>
    </section>
  </>;
}
